"""Controlled provider fixtures; real graph, storage, authentication and retention."""

from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select

from api.config import settings
from api.db import utcnow
from api.graph import store
from api.models import LogArtifact, Repository
from api.services.artifacts import (
    artifact_path,
    persist_log,
    purge_expired_logs,
    pytest_failure_links,
    redact,
)
from api.services.github import GitHub, RateLimited
from api.worker import run_once
from tests.conftest import register
from tests.test_indexing import connected


def test_download_redirect_does_not_forward_credentials_and_enforces_bounds(monkeypatch):
    api = GitHub("backend-only-token")
    api.client.close()
    signed = "https://results.actions.githubusercontent.com/job.txt?sig=temporary-secret"
    target = {"location": signed, "status": 302, "content": b"a test failed\n"}
    api.client = httpx.Client(
        base_url="https://api.github.com",
        headers={"Authorization": "Bearer backend-only-token"},
        transport=httpx.MockTransport(
            lambda req: httpx.Response(target["status"], headers={"location": target["location"]})
        ),
    )
    real_client = httpx.Client
    observed = []

    def download(req):
        observed.append(req)
        assert "authorization" not in req.headers and "cookie" not in req.headers
        return httpx.Response(200, content=target["content"])

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: real_client(**kwargs, transport=httpx.MockTransport(download)),
    )
    text, status = api.download_log("owner/repo", 123)
    assert text == "a test failed\n" and "Redacted" in status
    assert observed[0].url.host == "results.actions.githubusercontent.com"
    for location in [
        "http://results.actions.githubusercontent.com/x",
        "https://127.0.0.1/logs",
        "https://evil.example/logs",
        "https://results.actions.githubusercontent.com.evil.example/logs",
        "https://token@results.actions.githubusercontent.com/x",
    ]:
        target["location"] = location
        assert api.download_log("owner/repo", 123)[0] is None
    assert len(observed) == 1
    target["location"], target["content"] = signed, b"x" * 2000
    monkeypatch.setattr(settings(), "max_log_bytes", 1000)
    assert "size limit" in api.download_log("owner/repo", 123)[1]
    target["status"] = 410
    assert "410" in api.download_log("owner/repo", 123)[1]
    target["status"] = 429
    with pytest.raises(RateLimited):
        api.download_log("owner/repo", 123)
    monkeypatch.setattr(settings(), "max_log_downloads", 0)
    assert "budget" in api.download_log("owner/repo", 123)[1]
    api.client.close()


def test_redaction_masks_known_and_common_secrets(monkeypatch):
    monkeypatch.setattr(settings(), "github_token", "known-configured-value")
    text = """known-configured-value
AUTHORIZATION: Bearer bearer-value
password=hidden-value
API_KEY: hidden-api
https://user:hidden-password@example.com/path
ghp_abcdefghijklmnopqrstuvwxyz123456
AKIA1234567890123456
-----BEGIN RSA PRIVATE KEY-----
private data
-----END RSA PRIVATE KEY-----
\x1b[31mFAILED test_checkout service.py:12\x1b[0m
"""
    clean = redact(text)
    for secret in [
        "known-configured-value",
        "bearer-value",
        "hidden-value",
        "hidden-api",
        "hidden-password",
        "ghp_abcdefghijklmnopqrstuvwxyz123456",
        "AKIA1234567890123456",
        "private data",
    ]:
        assert secret not in clean
    assert "FAILED test_checkout service.py:12" in clean and "\x1b" not in clean


def test_real_archive_download_isolation_expiry_and_cleanup(client, db, monkeypatch):
    repo_id = connected(client)
    base = f"/api/repositories/{repo_id}"
    original = client.get(base).json()
    repo = db.get(Repository, repo_id)
    repo.source_type, repo.source = "github", "https://github.com/test/log-fixture"
    db.commit()
    monkeypatch.setattr(settings(), "github_token", "configured-secret-fixture")
    calls = []

    def get(self, path, params=None):
        self.requests += 1
        if path.endswith("/actions/runs"):
            return {
                "workflow_runs": [
                    {
                        "id": 8,
                        "name": "Tests",
                        "run_number": 1,
                        "run_attempt": 2,
                        "head_sha": "a" * 40,
                        "conclusion": "failure",
                        "status": "completed",
                        "html_url": "https://github.com/test/log-fixture/actions/runs/8",
                        "updated_at": "2026-01-01T00:00:00Z",
                    }
                ]
            }, False
        if path.endswith("/actions/runs/8/jobs"):
            return {
                "jobs": [
                    {
                        "id": 9,
                        "name": "pytest",
                        "conclusion": "failure",
                        "steps": [{"name": "Run tests", "conclusion": "failure"}],
                    }
                ]
            }, False
        return [], False

    def download(self, project, jid):
        calls.append((project, jid))
        self.log_downloads += 1
        return (
            "password=fixture-password\nconfigured-secret-fixture\nFAILED test_checkout service.py:12\n",
            "Archived",
        )

    monkeypatch.setattr(GitHub, "get", get)
    monkeypatch.setattr(GitHub, "download_log", download)
    client.post(base + "/jobs?kind=github-sync")
    run_once()
    current = client.get(base).json()
    assert client.get(base + "/jobs").json()[0]["status"] == "succeeded"
    assert calls == [("test/log-fixture", 9)]
    row = db.scalar(select(LogArtifact))
    path = artifact_path(row)
    assert path.stat().st_mode & 0o777 == 0o600
    assert (
        "fixture-password" not in path.read_text()
        and "configured-secret-fixture" not in path.read_text()
    )
    logs = client.get(base + "/history?kind=LogArtifact").json()["items"]
    assert len(logs) == 1 and logs[0]["artifact_id"] == row.id
    graph = client.get(base + "/graph").json()
    assert any(e["type"] == "PRODUCES" for e in graph["edges"])
    url = base + "/artifacts/" + row.id
    response = client.get(url)
    assert response.status_code == 200 and "FAILED test_checkout" in response.text
    assert (
        response.headers["content-type"].startswith("text/plain")
        and response.headers["cache-control"] == "no-store"
    )
    assert client.get(url, params={"revision": original["snapshot_id"]}).status_code == 404
    assert client.get(url, params={"branch": "unconnected"}).status_code == 404
    evidence_url = base + "/evidence/" + row.node_id
    evidence = client.get(evidence_url).json()
    assert "FAILED test_checkout" in evidence["content"] and "redaction" in evidence["notice"]
    queries = []
    original_query = store.query

    def counted_query(*args, **kwargs):
        queries.append(args[1])
        return original_query(*args, **kwargs)

    with monkeypatch.context() as counting:
        counting.setattr(store, "query", counted_query)
        result = client.post(base + "/context", json={"question": "Investigate pytest"}).json()
    assert len(queries) == result["diagnostics"]["graph_queries"]
    assert (
        result["diagnostics"]["graph_queries"]
        <= result["diagnostics"]["max_graph_queries"]
    )
    assert any("FAILED test_checkout" in c["content"] for c in result["evidence"])
    saved = client.get(base + "/conversations").json()[0]
    assert "FAILED test_checkout" not in str(saved)
    client.post(base + "/jobs?kind=github-sync")
    run_once()
    db.expire_all()
    assert len(list(db.scalars(select(LogArtifact)))) == 1
    # Expiration denies content even before the periodic worker removes the file.
    row = db.get(LogArtifact, row.id)
    row.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert client.get(url).status_code == 410
    assert client.get(evidence_url).json()["content"] == ""
    assert purge_expired_logs()["artifacts"] == 1 and not path.exists()
    assert purge_expired_logs()["artifacts"] == 0
    register(client, "outsider@example.com")
    assert client.get(url).status_code == 404
    for name in store.client().list_graphs():
        if name.startswith("gp_" + repo_id.replace("-", "")):
            store.delete_graph(name)
    assert current["snapshot_id"] != original["snapshot_id"]


def test_pytest_failure_links_require_exact_identity_commit_and_retained_content(client, db):
    repo_id = connected(client)
    repo = db.get(Repository, repo_id)
    nodes, _ = store.manifest(repo.graph_name)
    try:
        saved = persist_log(
            repo,
            "pytest:1",
            """FAILED test_service.py::test_checkout[param] - AssertionError
FAILED test_checkout
FAILED other/test_service.py::test_checkout - unrelated path
FAILED test_service.py::missing - absent declaration
""",
        )
        links = pytest_failure_links(repo, saved, nodes, repo.commit_sha)
        test = next(n for n in nodes if n["type"] == "TestCase")
        assert len(links) == 1 and links[0]["target"] == test["id"]
        assert links[0]["provenance"] == "pytest-failure-nodeid"
        assert pytest_failure_links(repo, saved, nodes, "a" * 40) == []
        assert pytest_failure_links(repo, saved, nodes + [test], repo.commit_sha) == []
        row = db.get(LogArtifact, saved["id"])
        path = artifact_path(row)
        path.write_text("FAILED test_service.py::test_checkout - tampered")
        assert pytest_failure_links(repo, saved, nodes, repo.commit_sha) == []
    finally:
        store.delete_graph(repo.graph_name)
