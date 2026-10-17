"""Bounded, resumable GitHub REST ingestion. No inference that references fix issues."""

import json
import re
import time
from types import SimpleNamespace
from urllib.parse import urlparse

import httpx
from sqlalchemy import select

from api.auth import audit
from api.config import settings
from api.db import SessionLocal, utcnow
from api.graph import store
from api.ingestion.python import PARSER_VERSION, build_graph, stable_id
from api.ingestion.sources import SourceError, github_url
from api.models import HistoryRecord, Job, Repository, SourceFile
from api.services.artifacts import (
    ArtifactLimitError,
    cached_log,
    persist_log,
    pytest_failure_links,
    redact,
)
from api.services.history_records import records_graph
from api.services.indexing import JobCancelled, checkpoint
from api.services.lifecycle import discard_unpublished
from api.services.revisions import history_fingerprint, publish_snapshot, state_for_branch
from api.services.runtime_config import log_policy


class RateLimited(SourceError):
    def __init__(self, seconds):
        self.seconds = min(max(int(seconds), 1), 3600)
        super().__init__(
            "GitHub rate limit reached. Sync will resume after the server retry window."
        )


def check_rate_limit(response):
    if response.status_code == 429 or (
        response.status_code == 403 and response.headers.get("x-ratelimit-remaining") == "0"
    ):
        retry = response.headers.get("retry-after", "")
        if retry.isdigit():
            delay = int(retry)
        else:
            try:
                delay = int(response.headers.get("x-ratelimit-reset", "0")) - int(
                    utcnow().timestamp()
                )
            except ValueError:
                delay = 60
        raise RateLimited(max(delay, 1))


class GitHub:
    def __init__(self, token=""):
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "GraphPilot/0.1",
        }
        if token:
            headers["Authorization"] = "Bearer " + token
        self.client = httpx.Client(
            base_url="https://api.github.com",
            headers=headers,
            timeout=httpx.Timeout(20, connect=5),
            follow_redirects=False,
        )
        self.requests = 0
        self.log_downloads = 0

    def download_log(self, project, job_id):
        """GitHub's job endpoint redirects to short-lived plain text storage.

        https://docs.github.com/en/rest/actions/workflow-jobs#download-job-logs-for-a-workflow-run
        No credentials or cookies cross the redirect boundary.
        """
        if (
            not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", project)
            or not str(job_id).isdigit()
        ):
            raise SourceError("Invalid GitHub log resource")
        policy = log_policy()
        if self.log_downloads >= policy["max_log_downloads"] or self.requests > 197:
            return None, "Log download budget reached; another sync can retry"
        self.log_downloads += 1
        self.requests += 1
        try:
            response = self.client.get(f"/repos/{project}/actions/jobs/{job_id}/logs")
            check_rate_limit(response)
            if response.status_code in {403, 404, 410}:
                return (
                    None,
                    f"Logs unavailable (GitHub HTTP {response.status_code}); permissions or retention may prevent access",
                )
            if response.status_code != 302:
                return None, f"Log download unavailable (GitHub HTTP {response.status_code})"
            location = response.headers.get("location", "")
            target = urlparse(location)
            host = target.hostname or ""
            if (
                target.scheme != "https"
                or target.username
                or target.password
                or target.port not in {None, 443}
                or not any(
                    host.endswith(suffix)
                    for suffix in (".actions.githubusercontent.com", ".blob.core.windows.net")
                )
            ):
                return None, "Log redirect was outside permitted GitHub storage hosts"
            self.requests += 1
            # Use a separate client so the backend GitHub token is never forwarded.
            with httpx.Client(
                timeout=httpx.Timeout(20, connect=5),
                follow_redirects=False,
                headers={"Accept-Encoding": "identity"},
            ) as downloads:
                deadline = time.monotonic() + 20
                with downloads.stream("GET", location) as download:
                    if download.status_code != 200:
                        return None, f"Log storage unavailable (HTTP {download.status_code})"
                    length = download.headers.get("content-length", "")
                    if length.isdigit() and int(length) > policy["max_log_bytes"]:
                        return None, "Log exceeds configured download size limit"
                    if download.headers.get("content-encoding", "identity").lower() != "identity":
                        return None, "Compressed log transfers are not accepted"
                    content = bytearray()
                    for chunk in download.iter_bytes(chunk_size=65536):
                        if time.monotonic() > deadline:
                            return None, "Log download exceeded the operation deadline"
                        content.extend(chunk)
                        if len(content) > policy["max_log_bytes"]:
                            return None, "Log exceeds configured download size limit"
            if b"\0" in content:
                return None, "Binary log content was rejected"
            return content.decode(
                "utf-8", errors="replace"
            ), "Redacted text archived; automated redaction may miss unknown secret formats"
        except RateLimited:
            raise
        except (httpx.HTTPError, ValueError):
            return None, "Log download failed; retry a later sync"

    def get(self, path, params=None):
        if not path.startswith("/repos/") or "://" in path or ".." in path:
            raise SourceError("Invalid GitHub API resource")
        for attempt in range(3):
            if self.requests >= 200:
                raise SourceError(
                    "GitHub sync request budget reached; retry to resume saved progress"
                )
            self.requests += 1
            try:
                with self.client.stream("GET", path, params=params) as response:
                    check_rate_limit(response)
                    if response.status_code in {404, 410}:
                        return None, False
                    if response.status_code in {502, 503, 504} and attempt < 2:
                        continue
                    if response.status_code != 200:
                        raise SourceError(
                            f"GitHub returned HTTP {response.status_code}. Check repository visibility and provider permissions."
                        )
                    deadline, content = time.monotonic() + 20, bytearray()
                    for chunk in response.iter_bytes(chunk_size=65536):
                        content.extend(chunk)
                        if len(content) > 5_000_000:
                            raise SourceError("GitHub response exceeded size budget")
                        if time.monotonic() > deadline:
                            raise SourceError("GitHub response exceeded the operation deadline")
                    try:
                        data = json.loads(content)
                    except ValueError:
                        raise SourceError("GitHub returned invalid JSON") from None
                    return data, 'rel="next"' in response.headers.get("link", "")
            except httpx.HTTPError:
                if attempt == 2:
                    raise SourceError("GitHub is unavailable. Retry to resume sync.") from None
        raise SourceError("GitHub request failed")


def history_node(repo, kind, key, **data):
    return {
        "id": stable_id(repo.id, repo.branch, kind, key),
        "type": kind,
        "name": str(data.pop("name", key))[:200],
        "repository_id": repo.id,
        "branch": repo.branch,
        "commit": repo.commit_sha or "",
        "indexing_version": PARSER_VERSION,
        "original_id": key,
        "provenance": "github-api",
        **data,
    }


def relation(source, target, kind):
    return {"source": source, "target": target, "type": kind, "provenance": "github-api"}


def save_records(
    repo_id, branch, records, cursor_key, page, more, job_id, worker_id, detail_update=None
):
    with SessionLocal() as db:
        job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
        if not job or job.worker_id != worker_id or job.cancel_requested or job.status != "running":
            raise JobCancelled()
        repo = db.get(Repository, repo_id)
        head = state_for_branch(db, repo, branch)
        state = dict(head.sync_state)
        pending = dict(state.get("pull_details", {}))
        for node, edges in records:
            row = db.get(HistoryRecord, node["id"])
            if not row:
                row = HistoryRecord(id=node["id"], repository_id=repo_id, branch=branch)
                db.add(row)
            elif node["type"] == "Commit":
                # A PR's sparse commit list must not erase immutable detail evidence.
                node = {**row.data, **{k: v for k, v in node.items() if v != ""}}
                edges = list({store.edge_id(e): e for e in row.relationships + edges}.values())
            if node["type"] == "PullRequest" and cursor_key == "pulls":
                same_version = row.data and row.data.get("timestamp") == node["timestamp"]
                if same_version:
                    edges = list({store.edge_id(e): e for e in row.relationships + edges}.values())
                    node["details_status"] = row.data.get("details_status", "pending")
                else:
                    node["details_status"] = "pending"
                if not same_version or node["details_status"] == "pending":
                    key = str(node["number"])
                    pending.setdefault(key, {"commits": 1, "files": 1})
                    if not same_version:
                        pending[key] = {"commits": 1, "files": 1}
                    if len(pending) > 1000:
                        raise SourceError("Pending PR details exceed the sync capacity")
            row.data, row.relationships = node, edges
        if cursor_key:
            cursors = dict(state.get("cursors", {}))
            cursors[cursor_key] = page + 1 if more else 0
            state["cursors"] = cursors
        if detail_update:
            key, kind, next_page, unavailable = detail_update
            progress = dict(pending[key])
            progress[kind] = next_page
            progress["unavailable"] = progress.get("unavailable", False) or unavailable
            if progress["commits"] == progress["files"] == 0:
                pending.pop(key)
            else:
                pending[key] = progress
        state["pull_details"] = pending
        head.sync_state = state
        db.commit()


def run_sync(job_id, worker_id):
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        base_repo = db.get(Repository, job.repository_id)
        branch = job.branch or base_repo.branch
        head = state_for_branch(db, base_repo, branch)
        # Capture this job's branch without changing the shared default branch.
        repo = SimpleNamespace(
            id=base_repo.id,
            name=base_repo.name,
            source=base_repo.source,
            source_type=base_repo.source_type,
            branch=branch,
            commit_sha=head.commit_sha,
            graph_name=head.graph_name,
            sync_state=dict(head.sync_state),
        )
        if repo.source_type != "github" or not repo.graph_name:
            raise SourceError("Index a GitHub repository before synchronizing history")
        github_url(repo.source)
        project = repo.source.removeprefix("https://github.com/")
        files = {
            r.path: r.parsed
            for r in db.scalars(
                select(SourceFile).where(
                    SourceFile.repository_id == repo.id, SourceFile.branch == repo.branch
                )
            )
        }
        code_nodes, code_edges, _ = build_graph(
            repo.id, repo.branch, repo.commit_sha, repo.name, files
        )
        previous_graph = repo.graph_name
        cursors = dict(repo.sync_state.get("cursors", {}))
    old_nodes, old_edges = store.manifest(previous_graph)
    api = GitHub(settings().github_token)
    base = f"/repos/{project}"
    rid = stable_id(repo.id, repo.branch, "Repository", repo.id)
    bid = stable_id(repo.id, repo.branch, "Branch", repo.branch)
    warnings = []

    def commit_record(item):
        sha = item["sha"]
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise SourceError("GitHub returned an invalid commit ID")
        details = item.get("commit", {})
        node = history_node(
            repo,
            "Commit",
            sha,
            name=details.get("message", "").split("\n")[0],
            sha=sha,
            commit=sha,
            body=details.get("message", "")[:4000],
            url=item.get("html_url", ""),
            timestamp=(details.get("committer") or {}).get("date", ""),
        )
        edges = [relation(bid, node["id"], "CONTAINS_COMMIT")]
        for issue in set(re.findall(r"(?<![\w/])#(\d+)", node["body"])):
            edges.append(
                relation(node["id"], stable_id(repo.id, repo.branch, "Issue", issue), "REFERENCES")
            )
        for file in item.get("files", []):
            if file.get("filename") in files:
                edges.append(
                    relation(
                        node["id"],
                        stable_id(repo.id, repo.branch, "File", file["filename"]),
                        "MODIFIES",
                    )
                )
        return node, edges

    def commit_details(item):
        node, edges = commit_record(item)
        with SessionLocal() as db:
            saved = db.get(HistoryRecord, node["id"])
            page = saved.data.get("detail_page", 1) if saved else 1
        # Immutable SHAs need full detail only once. File pages have independent
        # durable progress, even if the surrounding listing page is interrupted.
        for _ in range(4):
            if page == 0 or api.requests >= 190:
                break
            detail, more = api.get(
                base + "/commits/" + item["sha"], {"per_page": 100, "page": page}
            )
            node, edges = commit_record(detail or item)
            page = page + 1 if more else 0
            node["detail_page"] = page
            node["details_status"] = (
                "unavailable" if detail is None else "partial" if more else "complete"
            )
            save_records(repo.id, repo.branch, [(node, edges)], "", 0, False, job_id, worker_id)
        if page:
            warnings.append(
                f"Commit {item['sha'][:12]} has additional file pages; a later sync resumes detail progress"
            )
        return node, edges

    try:
        for endpoint in ["commits", "issues", "pulls", "actions/runs"]:
            page = cursors.get(endpoint, 1)
            if page == 0:
                page = 1  # A new job polls the latest page; stable IDs suppress duplicates.
            for _ in range(4):
                checkpoint(
                    job_id,
                    worker_id,
                    min(10 + api.requests, 80),
                    f"Synchronizing GitHub {endpoint}, page {page}",
                )
                params = {"per_page": 30, "page": page}
                if endpoint == "commits":
                    params["sha"] = repo.branch
                if endpoint == "actions/runs":
                    params["branch"] = repo.branch
                if endpoint in {"issues", "pulls"}:
                    params.update(state="all", sort="updated", direction="desc")
                data, more = api.get(base + "/" + endpoint, params)
                if data is None:
                    warnings.append(f"{endpoint} is unavailable or has been deleted")
                    save_records(repo.id, repo.branch, [], endpoint, page, False, job_id, worker_id)
                    break
                items = data.get("workflow_runs", []) if isinstance(data, dict) else data
                records = []
                for item in items:
                    if endpoint == "commits":
                        # Commit detail supplies real changed-file references.
                        records.append(commit_details(item))
                    elif endpoint == "issues":
                        if "pull_request" in item:
                            continue
                        key = str(item["number"])
                        node = history_node(
                            repo,
                            "Issue",
                            key,
                            name=f"#{key} {item['title']}",
                            number=item["number"],
                            body=(item.get("body") or "")[:4000],
                            status=item["state"],
                            url=item["html_url"],
                            timestamp=item["updated_at"],
                        )
                        records.append((node, [relation(rid, node["id"], "RELATED_TO")]))
                    elif endpoint == "pulls":
                        key = str(item["number"])
                        node = history_node(
                            repo,
                            "PullRequest",
                            key,
                            name=f"PR #{key} {item['title']}",
                            number=item["number"],
                            body=(item.get("body") or "")[:4000],
                            status="merged" if item.get("merged_at") else item["state"],
                            details_scope="GitHub API listings: up to 250 PR commits and 3000 changed files; larger histories are incomplete",
                            url=item["html_url"],
                            timestamp=item["updated_at"],
                        )
                        edges = [relation(rid, node["id"], "RELATED_TO")]
                        for issue in set(re.findall(r"(?<![\w/])#(\d+)", node["body"])):
                            edges.append(
                                relation(
                                    node["id"],
                                    stable_id(repo.id, repo.branch, "Issue", issue),
                                    "REFERENCES",
                                )
                            )
                        records.append((node, edges))
                    else:
                        key = str(item["id"])
                        node = history_node(
                            repo,
                            "WorkflowRun",
                            key,
                            name=f"{item.get('name') or 'Workflow'} #{item['run_number']}",
                            status=item.get("conclusion") or item["status"],
                            url=item["html_url"],
                            timestamp=item["updated_at"],
                            sha=item["head_sha"],
                        )
                        edges = [
                            relation(
                                node["id"],
                                stable_id(repo.id, repo.branch, "Commit", item["head_sha"]),
                                "TRIGGERED_BY",
                            )
                        ]
                        if item.get("conclusion") == "failure":
                            jobs, jobs_more = api.get(
                                base + f"/actions/runs/{key}/jobs",
                                {"filter": "latest", "per_page": 100},
                            )
                            failed = [
                                j
                                for j in (jobs or {}).get("jobs", [])
                                if j.get("conclusion") == "failure"
                            ]
                            if jobs_more or len(failed) > 3:
                                warnings.append(
                                    f"Workflow {key}: logs select at most three failed jobs from the first 100 jobs"
                                )
                            node["summary"] = redact(
                                "\n".join(
                                    f"{j['name']}: "
                                    + ", ".join(
                                        s["name"]
                                        for s in j.get("steps", [])
                                        if s.get("conclusion") == "failure"
                                    )
                                    for j in failed
                                )
                            )[:4000]
                            log_status = []
                            for failed_job in failed[:3]:
                                jid = failed_job.get("id")
                                if not str(jid).isdigit():
                                    log_status.append(
                                        "GitHub did not supply a valid job ID for logs"
                                    )
                                    continue
                                checkpoint(
                                    job_id,
                                    worker_id,
                                    min(10 + api.requests, 80),
                                    "Retrieving selected CI failure logs",
                                )
                                attempt = item.get("run_attempt", 1)
                                source_id = f"{jid}:{attempt}"
                                saved = cached_log(repo, source_id)
                                if saved is None:
                                    text, status = api.download_log(project, jid)
                                    log_status.append(status)
                                    if text is not None:
                                        try:
                                            saved = persist_log(repo, source_id, text)
                                        except ArtifactLimitError:
                                            log_status.append(
                                                "Redacted log exceeds the current archive budget; no file was stored"
                                            )
                                else:
                                    log_status.append(
                                        "Previously archived; original retention deadline applies"
                                    )
                                if saved is not None:
                                    log_node = history_node(
                                        repo,
                                        "LogArtifact",
                                        saved["id"],
                                        name=f"CI log: {failed_job['name']}",
                                        artifact_id=saved["id"],
                                        commit=item["head_sha"],
                                        size_bytes=saved["size_bytes"],
                                        content_hash=saved["content_hash"],
                                        expires_at=saved["expires_at"],
                                        url=item["html_url"],
                                        timestamp=item["updated_at"],
                                        status="redacted",
                                        redaction="Best effort; unknown secret formats may remain",
                                    )
                                    records.append(
                                        (
                                            log_node,
                                            [relation(node["id"], log_node["id"], "PRODUCES")]
                                            + pytest_failure_links(
                                                repo, saved, code_nodes, item["head_sha"]
                                            ),
                                        )
                                    )
                            node["log_status"] = (
                                "; ".join(log_status)
                                or "No failed jobs with available log references"
                            )
                        records.append((node, edges))
                save_records(repo.id, repo.branch, records, endpoint, page, more, job_id, worker_id)
                if not more:
                    break
                page += 1
            else:
                warnings.append(
                    f"{endpoint} has additional pages. A later sync resumes at the saved page."
                )
        # Detail cursors are independent of the moving PR listing. Save every
        # page atomically with its evidence, so interruptions do not lose pages.
        detail_pages = 0
        while detail_pages < 12 and api.requests < 190:
            with SessionLocal() as db:
                head = state_for_branch(db, db.get(Repository, repo.id), repo.branch)
                pending = head.sync_state.get("pull_details", {})
                if not pending:
                    break
                key = sorted(pending, key=int)[0]
                progress = pending[key]
                kind = "commits" if progress["commits"] else "files"
                page = progress[kind]
                record = db.get(HistoryRecord, stable_id(repo.id, repo.branch, "PullRequest", key))
                node, edges = dict(record.data), list(record.relationships)
            checkpoint(
                job_id,
                worker_id,
                min(10 + api.requests, 85),
                f"Synchronizing PR #{key} {kind}, page {page}",
            )
            items, more = api.get(base + f"/pulls/{key}/{kind}", {"per_page": 100, "page": page})
            records = []
            for item in items or []:
                if kind == "commits":
                    cn, ce = commit_record(item)
                    records.append((cn, ce))
                    edges.append(relation(node["id"], cn["id"], "REFERENCES"))
                elif item.get("filename") in files:
                    edges.append(
                        relation(
                            node["id"],
                            stable_id(repo.id, repo.branch, "File", item["filename"]),
                            "MODIFIES",
                        )
                    )
            next_page = page + 1 if more else 0
            complete = not next_page and not progress["files" if kind == "commits" else "commits"]
            node["details_status"] = (
                "unavailable"
                if complete and (items is None or progress.get("unavailable"))
                else "complete"
                if complete
                else "partial"
            )
            records.append((node, list({store.edge_id(e): e for e in edges}.values())))
            save_records(
                repo.id,
                repo.branch,
                records,
                "",
                0,
                False,
                job_id,
                worker_id,
                detail_update=(key, kind, next_page, items is None),
            )
            detail_pages += 1
            if items is None:
                warnings.append(f"PR #{key} {kind} are unavailable or have been deleted")
        with SessionLocal() as db:
            history_nodes, history_edges = records_graph(db, repo)
            head = state_for_branch(db, db.get(Repository, repo.id), repo.branch)
            if head.sync_state.get("pull_details"):
                warnings.append(
                    "PR details have additional pages; a later sync resumes saved detail cursors"
                )
        # Only real existing endpoints may be linked. Dangling references remain unknown.
        all_nodes = code_nodes + history_nodes
        ids = {n["id"] for n in all_nodes}
        published_history_edges = [
            e for e in history_edges if e["source"] in ids and e["target"] in ids
        ]
        all_edges = code_edges + published_history_edges
        new_graph = store.graph_name(repo.id, repo.branch, "history-" + job_id)
        published = False
        try:
            checkpoint(job_id, worker_id, 90, "Publishing connected historical evidence")
            store.update_snapshot(
                previous_graph,
                new_graph,
                old_nodes,
                old_edges,
                all_nodes,
                all_edges,
            )
            count = store.query(new_graph, "MATCH (n:Entity) RETURN count(n)")[0][0]
            edge_count = store.query(new_graph, "MATCH ()-[r]->() RETURN count(r)")[0][0]
            if count != len(all_nodes) or edge_count != len(all_edges):
                raise SourceError("Historical graph integrity validation failed")
            with SessionLocal() as db:
                job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
                if job.worker_id != worker_id or job.cancel_requested or job.status != "running":
                    raise JobCancelled()
                fresh = db.get(Repository, repo.id)
                head = state_for_branch(db, fresh, repo.branch)
                stats = {
                    **head.stats,
                    "nodes": len(all_nodes),
                    "edges": len(all_edges),
                    "history_fingerprint": history_fingerprint(
                        history_nodes, published_history_edges
                    ),
                }
                sync_state = {
                    **head.sync_state,
                    "last_synced_at": utcnow().isoformat(),
                    "warnings": warnings,
                    "history_entities": len(history_nodes),
                    "requests": api.requests,
                    "log_downloads": api.log_downloads,
                }
                publish_snapshot(
                    db,
                    fresh,
                    repo.branch,
                    "github-sync",
                    new_graph,
                    repo.commit_sha,
                    stats,
                    sync_state,
                )
                job.status, job.progress, job.message, job.finished_at = (
                    "succeeded",
                    100,
                    "GitHub metadata synchronized; inspect coverage warnings",
                    utcnow(),
                )
                job.result = sync_state
                audit(
                    db,
                    job.requested_by,
                    "repository.github_synced",
                    repo.id,
                    entities=len(history_nodes),
                    requests=api.requests,
                )
                db.commit()
                published = True
        finally:
            if not published:
                discard_unpublished(repo.id, new_graph)
    finally:
        api.client.close()
