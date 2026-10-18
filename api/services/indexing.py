import hashlib
import shutil

from sqlalchemy import delete, select

from api.auth import audit
from api.config import settings
from api.db import SessionLocal, utcnow
from api.graph.store import create_graph, graph_name, manifest, query, update_snapshot
from api.ingestion.python import PARSER_VERSION, build_graph, parse_file
from api.ingestion.sources import SourceError, prune_snapshot, read_files, snapshot
from api.models import Job, Repository, SourceFile
from api.services.lifecycle import discard_unpublished
from api.services.revisions import history_fingerprint, publish_snapshot, state_for_branch


class JobCancelled(Exception):
    pass


def checkpoint(job_id, worker_id, progress, message):
    with SessionLocal() as db:
        job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
        if not job or job.worker_id != worker_id or job.status != "running" or job.cancel_requested:
            raise JobCancelled()
        from datetime import timedelta

        if job.lease_until and utcnow() > job.lease_until - timedelta(seconds=60):
            raise SourceError("Indexing exceeded its configured operation timeout")
        job.progress, job.message = progress, message
        db.commit()


def run_index(job_id: str, worker_id: str):
    cfg = settings()
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        repo = db.get(Repository, job.repository_id)
        repo_id, branch, source_type, source, name = (
            repo.id,
            job.branch or repo.branch,
            repo.source_type,
            repo.source,
            repo.name,
        )
        state = state_for_branch(db, repo, branch, create=True)
        previous_graph, previous_commit = state.graph_name, state.commit_sha
        previous_stats, sync_state = dict(state.stats), dict(state.sync_state)
        old_rows = db.scalars(
            select(SourceFile).where(
                SourceFile.repository_id == repo_id, SourceFile.branch == branch
            )
        ).all()
        old_files = {row.path: row.parsed for row in old_rows}
        github_user, github_repository_id = (
            repo.github_connection_user_id,
            repo.github_repository_id,
        )
    # Carry forward only published history, never staged pages from an
    # interrupted GitHub sync that has not published its graph.
    old_nodes, old_edges = manifest(previous_graph) if previous_graph else ([], [])
    history_nodes = [
        n
        for n in old_nodes
        if n["type"] not in {"Repository", "Branch", "File", "Function", "Class", "TestCase"}
    ]
    history_ids = {n["id"] for n in history_nodes}
    history_edges = [
        e for e in old_edges if e["source"] in history_ids or e["target"] in history_ids
    ]
    work = cfg.data_dir.resolve() / "work" / job_id
    tree = work / "tree"
    new_graph = None
    created_fingerprint = None
    published = False
    try:
        checkpoint(job_id, worker_id, 5, "Reading a safe source snapshot")
        if work.exists():
            shutil.rmtree(work)
        source_credentials = {}
        if github_user:
            from fastapi import HTTPException

            from api.services.github_connection import repository_token

            try:
                source_credentials["github_token"] = repository_token(
                    github_user, github_repository_id
                )
            except HTTPException:
                raise SourceError(
                    "GitHub access changed. Reconnect the account and check selected repositories."
                ) from None
        commit, branch = snapshot(source_type, source, branch, tree, **source_credentials)
        text_files = read_files(tree)
        checkpoint(job_id, worker_id, 20, f"Analyzing {len(text_files)} text files")
        files, changed, skipped = {}, [], 0
        tree_hash = hashlib.sha256()
        for i, (path, content) in enumerate(sorted(text_files.items())):
            content_hash = hashlib.sha256(content.encode()).hexdigest()
            tree_hash.update(f"{path}\0{content_hash}\0{PARSER_VERSION}".encode())
            old = old_files.get(path)
            if old and old["hash"] == content_hash and old.get("parser_version") == PARSER_VERSION:
                files[path] = old
                skipped += 1
            else:
                files[path] = {
                    "hash": content_hash,
                    # LF-only line count, matching AST line numbers and the
                    # shared source-range reader. U+2028/U+2029/CR stay inline.
                    "lines": content.count("\n")
                    + (0 if not content or content.endswith("\n") else 1),
                    "parser_version": PARSER_VERSION,
                    "parsed": parse_file(path, content),
                }
                changed.append(path)
            if i % 20 == 0:
                checkpoint(
                    job_id,
                    worker_id,
                    20 + int(45 * (i + 1) / max(len(text_files), 1)),
                    f"Parsed {i + 1}/{len(text_files)} files",
                )
        fingerprint = tree_hash.hexdigest()
        if commit == "archive":
            commit = fingerprint
        deleted = sorted(set(old_files) - set(files))
        nodes, edges, stats = build_graph(repo_id, branch, commit, name, files)
        nodes += history_nodes
        node_ids = {n["id"] for n in nodes}
        edges += [e for e in history_edges if e["source"] in node_ids and e["target"] in node_ids]
        stats["nodes"], stats["edges"] = len(nodes), len(edges)
        stats.update(
            {
                "tree_hash": fingerprint,
                "history_fingerprint": history_fingerprint(history_nodes, history_edges),
                "parsed_files": len(changed),
                "skipped_files": skipped,
                "deleted_files": len(deleted),
                "semantic_languages": ["Python"],
                "file_only_languages": "All other UTF-8 text files",
                "parser_version": PARSER_VERSION,
            }
        )
        checkpoint(job_id, worker_id, 70, "Writing and validating FalkorDB snapshot")
        no_change = (
            previous_graph
            and not changed
            and not deleted
            and previous_commit == commit
            and previous_stats.get("history_fingerprint", "") == stats["history_fingerprint"]
        )
        if no_change:
            new_graph = previous_graph
            stats["graph_writes"] = 0
        else:
            new_graph = graph_name(repo_id, branch, commit + job_id)
            if previous_graph and old_files:
                delta = update_snapshot(
                    previous_graph, new_graph, old_nodes, old_edges, nodes, edges
                )
                stats["graph_writes"] = sum(delta.values())
                stats["delta"] = delta
            else:
                create_graph(new_graph, nodes, edges)
                stats["graph_writes"] = len(nodes) + len(edges)
            count = query(new_graph, "MATCH (n:Entity) RETURN count(n)")[0][0]
            edge_count = query(new_graph, "MATCH ()-[r]->() RETURN count(r)")[0][0]
            if count != len(nodes) or edge_count != len(edges):
                raise SourceError("Graph integrity validation failed")
        artifact = cfg.data_dir.resolve() / "snapshots" / repo_id / fingerprint
        artifact.parent.mkdir(parents=True, exist_ok=True)
        if not artifact.exists():
            prune_snapshot(tree, text_files)
            shutil.move(str(tree), str(artifact))
            created_fingerprint = fingerprint
        checkpoint(job_id, worker_id, 95, "Publishing verified snapshot")
        with SessionLocal() as db:
            job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
            if job.worker_id != worker_id or job.status != "running" or job.cancel_requested:
                raise JobCancelled()
            repo = db.get(Repository, repo_id)
            # Explicit fencing: stale workers may not publish after losing ownership.
            if (job.branch or repo.branch) != branch:
                raise SourceError("Repository branch changed during indexing; retry")
            publish_snapshot(db, repo, branch, "index", new_graph, commit, stats, sync_state)
            for path in deleted:
                db.execute(
                    delete(SourceFile).where(
                        SourceFile.repository_id == repo_id,
                        SourceFile.branch == branch,
                        SourceFile.path == path,
                    )
                )
            for path in changed:
                row = db.scalar(
                    select(SourceFile).where(
                        SourceFile.repository_id == repo_id,
                        SourceFile.branch == branch,
                        SourceFile.path == path,
                    )
                )
                if row is None:
                    row = SourceFile(repository_id=repo_id, branch=branch, path=path)
                    db.add(row)
                row.content_hash, row.parser_version, row.parsed = (
                    files[path]["hash"],
                    PARSER_VERSION,
                    files[path],
                )
            job.status, job.progress, job.finished_at = "succeeded", 100, utcnow()
            job.message = (
                "No source changes; existing snapshot retained"
                if no_change
                else "Index complete and graph validated"
            )
            job.result = stats
            audit(
                db,
                job.requested_by,
                "repository.indexed",
                repo_id,
                job_id=job_id,
                commit=commit,
                parsed_files=len(changed),
                skipped_files=skipped,
            )
            db.commit()
            published = True
    finally:
        if new_graph and not published and new_graph != previous_graph:
            discard_unpublished(repo_id, new_graph, created_fingerprint)
        shutil.rmtree(work, ignore_errors=True)
