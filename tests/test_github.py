"""Synthetic, recorded-shape GitHub REST fixtures; no production data is mocked."""

import httpx
import pytest
from sqlalchemy import select

from api.graph import store
from api.models import HistoryRecord, Job, Repository
from api.services.github import GitHub, RateLimited, SourceError
from api.worker import run_once
from tests.test_indexing import connected

SHA = "a" * 40
STAMP = "2026-01-02T00:00:00Z"


def test_github_history_links_dedup_sync_resume_and_reindex(client, db, monkeypatch):
    repo_id = connected(client)
    repo = db.get(Repository, repo_id)
    repo.source_type, repo.source = "github", "https://github.com/test/reference"
    db.commit()
    seen = []

    def get(self, path, params=None):
        self.requests += 1
        seen.append((path, params))
        if path.endswith("/commits/" + SHA):
            return {
                "sha": SHA,
                "commit": {"message": "Handle order #7", "committer": {"date": STAMP}},
                "html_url": "https://github.com/test/reference/commit/" + SHA,
                "files": [{"filename": "service.py"}],
            }, False
        if path.endswith("/commits") and "/pulls/" not in path:
            return (
                [
                    {
                        "sha": SHA,
                        "commit": {"message": "Handle order #7"},
                        "html_url": "https://github.com/test/reference/commit/" + SHA,
                    }
                ],
                False,
            )
        if path.endswith("/issues"):
            if params["page"] == 1:
                return [
                    {
                        "number": 7,
                        "title": "Order fails",
                        "body": "checkout fails",
                        "state": "open",
                        "html_url": "https://github.com/test/reference/issues/7",
                        "updated_at": STAMP,
                    }
                ], True
            return [], False
        if path.endswith("/pulls"):
            return [
                {
                    "number": 8,
                    "title": "Order change",
                    "body": "References #7 (not verified as a fix)",
                    "state": "closed",
                    "merged_at": STAMP,
                    "html_url": "https://github.com/test/reference/pull/8",
                    "updated_at": STAMP,
                }
            ], False
        if path.endswith("/pulls/8/commits"):
            return [
                {
                    "sha": SHA,
                    "commit": {"message": "Handle order #7"},
                    "html_url": "https://github.com/test/reference/commit/" + SHA,
                }
            ], False
        if path.endswith("/pulls/8/files"):
            return [{"filename": "service.py"}], False
        if path.endswith("/actions/runs"):
            return {
                "workflow_runs": [
                    {
                        "id": 9,
                        "name": "Tests",
                        "run_number": 2,
                        "head_sha": SHA,
                        "conclusion": "failure",
                        "status": "completed",
                        "html_url": "https://github.com/test/reference/actions/runs/9",
                        "updated_at": STAMP,
                    }
                ]
            }, False
        if path.endswith("/actions/runs/9/jobs"):
            return {
                "jobs": [
                    {
                        "name": "pytest",
                        "conclusion": "failure",
                        "steps": [{"name": "Run pytest", "conclusion": "failure"}],
                    }
                ]
            }, False
        raise AssertionError(path)

    monkeypatch.setattr(GitHub, "get", get)
    base = f"/api/repositories/{repo_id}"
    assert client.post(base + "/jobs?kind=github-sync").status_code == 201
    run_once()
    jobs = client.get(base + "/jobs").json()
    assert jobs[0]["status"] == "succeeded", jobs
    db.expire_all()
    repo = db.get(Repository, repo_id)
    history = client.get(base + "/history").json()
    assert {n["type"] for n in history["items"]} == {
        "Commit",
        "PullRequest",
        "Issue",
        "WorkflowRun",
    }
    assert any(path.endswith("/issues") and params["page"] == 2 for path, params in seen)
    graph = store.subgraph(repo.graph_name, 200)
    assert any(e["type"] == "REFERENCES" for e in graph["edges"])
    assert any(e["type"] == "TRIGGERED_BY" for e in graph["edges"])
    commit = next(n for n in graph["nodes"] if n["type"] == "Commit")
    assert commit["timestamp"] == STAMP
    assert any(e["type"] == "MODIFIES" and e["source"] == commit["id"] for e in graph["edges"])
    assert not any(e["type"] == "ADDRESSES" for e in graph["edges"])
    count = len(list(db.scalars(select(HistoryRecord))))
    client.post(base + "/jobs?kind=github-sync")
    run_once()
    db.expire_all()
    assert len(list(db.scalars(select(HistoryRecord)))) == count
    # An unchanged source scan after history sync preserves historical nodes.
    repo = db.get(Repository, repo_id)
    assert store.query(repo.graph_name, "MATCH (n:WorkflowRun) RETURN count(n)")[0][0] == 1
    assert repo.sync_state["log_downloads"] == 0
    # Saved cursor is explicit and inspected on the next sync.
    repo.sync_state = {**repo.sync_state, "cursors": {"issues": 3}}
    db.commit()
    seen.clear()
    client.post(base + "/jobs?kind=github-sync")
    run_once()
    assert any(path.endswith("/issues") and params["page"] == 3 for path, params in seen)
    for name in store.client().list_graphs():
        if name.startswith("gp_" + repo_id.replace("-", "")):
            store.delete_graph(name)


def test_rate_limits_unavailable_resources_and_error_redaction():
    api = GitHub()
    api.client.close()

    def handler(request):
        if request.url.path.endswith("/missing"):
            return httpx.Response(404)
        return httpx.Response(429, headers={"Retry-After": "17"}, text="secret must never surface")

    api.client = httpx.Client(
        base_url="https://api.github.com", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(RateLimited) as raised:
        api.get("/repos/a/b/issues")
    assert raised.value.seconds == 17 and "secret" not in str(raised.value)
    assert api.get("/repos/a/b/missing") == (None, False)
    with pytest.raises(SourceError):
        api.get("http://127.0.0.1/secrets")
    api.client.close()


def test_pull_detail_pages_resume_outside_listing_and_refresh_mutable_files(
    client, db, monkeypatch
):
    repo_id = connected(client)
    repo = db.get(Repository, repo_id)
    repo.source_type, repo.source = "github", "https://github.com/test/reference"
    db.commit()
    version, seen = [STAMP], []

    def get(self, path, params=None):
        self.requests += 1
        seen.append((path, params))
        if path.endswith("/pulls"):
            return [
                {
                    "number": 8,
                    "title": "Paged change",
                    "body": "",
                    "state": "open",
                    "html_url": "https://github.com/test/reference/pull/8",
                    "updated_at": version[0],
                }
            ], False
        if path.endswith("/pulls/8/commits"):
            page = params["page"]
            return [{"sha": f"{page:040x}", "commit": {"message": f"Page {page}"}}], page < 13
        if path.endswith("/pulls/8/files"):
            return [{"filename": "service.py" if version[0] == STAMP else "math_ops.py"}], False
        if path.endswith("/actions/runs"):
            return {"workflow_runs": []}, False
        return [], False

    monkeypatch.setattr(GitHub, "get", get)
    base = f"/api/repositories/{repo_id}"
    try:
        assert client.post(base + "/jobs?kind=github-sync").status_code == 201
        assert run_once()
        db.expire_all()
        repo = db.get(Repository, repo_id)
        assert repo.sync_state["pull_details"]["8"]["commits"] == 13
        first_graph = repo.graph_name
        assert client.post(base + "/jobs?kind=github-sync").status_code == 201
        assert run_once()
        db.expire_all()
        repo = db.get(Repository, repo_id)
        assert repo.sync_state["pull_details"] == {}
        assert store.query(repo.graph_name, "MATCH (n:Commit) RETURN count(n)")[0][0] == 13
        pr = next(
            n for n in client.get(base + "/history").json()["items"] if n["type"] == "PullRequest"
        )
        assert pr["details_status"] == "complete"
        assert len([p for p, _ in seen if p.endswith("/pulls/8/commits")]) == 13
        # Unchanged PR details are not repeatedly fetched on subsequent polls.
        seen.clear()
        client.post(base + "/jobs?kind=github-sync")
        run_once()
        assert not any("/pulls/8/" in p for p, _ in seen)
        # A changed PR starts a new detail generation and removes stale file edges.
        version[0] = "2026-01-03T00:00:00Z"
        for _ in range(2):
            client.post(base + "/jobs?kind=github-sync")
            run_once()
        db.expire_all()
        repo = db.get(Repository, repo_id)
        paths = store.query(
            repo.graph_name, "MATCH (n:PullRequest)-[:MODIFIES]->(f:File) RETURN f.path"
        )
        assert paths == [["math_ops.py"]]
        assert store.query(first_graph, "MATCH (n:Commit) RETURN count(n)")[0][0] == 12
    finally:
        for name in store.client().list_graphs():
            if name.startswith("gp_" + repo_id.replace("-", "")):
                store.delete_graph(name)


def test_rate_limited_worker_defers_and_preserves_cursor(client, db, monkeypatch):
    repo_id = connected(client)
    repo = db.get(Repository, repo_id)
    repo.source_type, repo.source = "github", "https://github.com/test/reference"
    repo.sync_state = {"cursors": {"commits": 2}}
    db.commit()

    def limited(*args, **kwargs):
        raise RateLimited(60)

    monkeypatch.setattr(GitHub, "get", limited)
    job = client.post(f"/api/repositories/{repo_id}/jobs?kind=github-sync").json()
    run_once()
    db.expire_all()
    row = db.get(Job, job["id"])
    assert row.status == "queued" and row.attempts == 1
    assert db.get(Repository, repo_id).sync_state["cursors"]["commits"] == 2
    for name in store.client().list_graphs():
        if name.startswith("gp_" + repo_id.replace("-", "")):
            store.delete_graph(name)


def test_commit_file_detail_pages_survive_rate_limit_and_skip_immutable_reloads(
    client, db, monkeypatch
):
    repo_id = connected(client)
    repo = db.get(Repository, repo_id)
    repo.source_type, repo.source = "github", "https://github.com/test/reference"
    db.commit()
    pages, limited = [], [False]

    def get(self, path, params=None):
        self.requests += 1
        if path.endswith("/commits/" + SHA):
            page = params["page"]
            pages.append(page)
            if page == 5 and not limited[0]:
                limited[0] = True
                raise RateLimited(17)
            return {
                "sha": SHA,
                "commit": {"message": "Paged files"},
                "files": [{"filename": "service.py" if page <= 4 else "math_ops.py"}],
            }, page < 6
        if path.endswith("/commits"):
            return [{"sha": SHA, "commit": {"message": "Paged files"}}], False
        if path.endswith("/actions/runs"):
            return {"workflow_runs": []}, False
        return [], False

    monkeypatch.setattr(GitHub, "get", get)
    base = f"/api/repositories/{repo_id}"
    try:
        client.post(base + "/jobs?kind=github-sync")
        run_once()
        assert pages == [1, 2, 3, 4]
        queued = client.post(base + "/jobs?kind=github-sync").json()
        run_once()
        db.expire_all()
        job = db.get(Job, queued["id"])
        assert job.status == "queued"
        from api.db import utcnow

        job.available_at = utcnow()
        db.commit()
        run_once()
        assert pages == [1, 2, 3, 4, 5, 5, 6]
        db.expire_all()
        repo = db.get(Repository, repo_id)
        paths = store.query(
            repo.graph_name, "MATCH (c:Commit)-[:MODIFIES]->(f:File) RETURN f.path ORDER BY f.path"
        )
        assert paths == [["math_ops.py"], ["service.py"]]
        node = next(
            n for n in client.get(base + "/history").json()["items"] if n["type"] == "Commit"
        )
        assert node["details_status"] == "complete" and node["detail_page"] == 0
        client.post(base + "/jobs?kind=github-sync")
        run_once()
        assert pages == [1, 2, 3, 4, 5, 5, 6]
    finally:
        for name in store.client().list_graphs():
            if name.startswith("gp_" + repo_id.replace("-", "")):
                store.delete_graph(name)
