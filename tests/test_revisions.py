"""Real PostgreSQL/FalkorDB branch and immutable evidence integration checks."""

import subprocess

import pytest
from sqlalchemy import select

from api.config import settings
from api.graph import store
from api.models import Membership, Repository, Snapshot, SourceFile
from api.services.github import GitHub
from api.worker import run_once
from tests.conftest import register
from tests.test_indexing import archive_bytes, connected


@pytest.fixture
def branch_repo(client, db, tmp_path, monkeypatch):
    source = tmp_path / "branches"
    source.mkdir()

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(source), *args], check=True, capture_output=True, text=True
        ).stdout.strip()

    git("init", "-b", "main")
    git("config", "user.name", "Branch fixture")
    git("config", "user.email", "fixture@example.com")
    (source / "service.py").write_text("def original():\n    return 'main evidence'\n")
    git("add", ".")
    git("commit", "-m", "Main evidence")
    git("checkout", "-b", "feature/evidence")
    (source / "service.py").write_text("def feature_only():\n    return 'branch evidence'\n")
    git("add", ".")
    git("commit", "-m", "Feature evidence")
    git("checkout", "main")
    monkeypatch.setattr(settings(), "allowed_local_roots", [tmp_path])
    owner = register(client)
    response = client.post(
        "/api/repositories", json={"source_type": "local", "source": str(source)}
    )
    assert response.status_code == 201, response.text
    repo_id = response.json()["repository"]["id"]
    assert run_once()
    yield repo_id, source, git, owner
    for name in store.client().list_graphs():
        if name.startswith("gp_" + repo_id.replace("-", "")):
            store.delete_graph(name)


def test_branches_and_old_source_remain_independent(client, db, branch_repo):
    repo_id, source, git, _ = branch_repo
    base = f"/api/repositories/{repo_id}"
    initial = client.get(base).json()
    original = client.get(base + "/search?q=original").json()["results"][0]
    old = {"branch": "main", "revision": initial["snapshot_id"]}
    assert old["revision"]
    for invalid in ("a..b", "a//b", "a.lock", "a/.hidden", "branch/", "branch."):
        assert client.post(base + "/branches", json={"branch": invalid}).status_code == 422
    response = client.post(base + "/branches", json={"branch": "feature/evidence"})
    assert response.status_code == 201, response.text
    assert response.json()["job"]["branch"] == "feature/evidence"
    assert client.post(base + "/jobs").status_code == 409
    assert run_once()
    feature = {"branch": "feature/evidence"}
    feature_head = client.get(base, params=feature).json()
    assert feature_head["status"] == "ready"
    assert feature_head["commit_sha"] != initial["commit_sha"]
    found = client.get(base + "/search", params=feature | {"q": "feature_only"}).json()["results"][
        0
    ]
    assert client.get(base + "/search?q=feature_only").json()["results"] == []
    assert client.get(base + "/search", params=feature | {"q": "original"}).json()["results"] == []
    assert client.get(base + f"/evidence/{found['id']}").status_code == 404
    assert (
        "branch evidence"
        in client.get(base + f"/evidence/{found['id']}", params=feature).json()["content"]
    )
    assert client.get(base, params=feature | {"revision": old["revision"]}).status_code == 404
    db.expire_all()
    assert db.get(Repository, repo_id).branch == "main"
    assert db.get(Repository, repo_id).commit_sha == initial["commit_sha"]
    assert {r.branch for r in db.scalars(select(SourceFile))} == {"main", "feature/evidence"}

    (source / "service.py").write_text("def replacement():\n    return 'new main evidence'\n")
    git("add", ".")
    git("commit", "-m", "Replace main symbol")
    assert client.post(base + "/jobs").status_code == 201
    assert run_once()
    current = client.get(base).json()
    assert current["snapshot_id"] != old["revision"]
    assert client.get(base + f"/evidence/{original['id']}").status_code == 404
    evidence = client.get(base + f"/evidence/{original['id']}", params=old).json()
    assert evidence["historical"] and evidence["commit"] == initial["commit_sha"]
    assert "main evidence" in evidence["content"] and "replacement" not in evidence["content"]
    assert client.get(base, params=old).json()["historical"]
    assert client.get(base, params=feature).json()["snapshot_id"] == feature_head["snapshot_id"]
    historical_graph = client.get(base + "/graph", params=old).json()
    assert any(n["id"] == original["id"] for n in historical_graph["nodes"])
    assert client.post(base + "/jobs", params=old).status_code == 422
    context = client.post(base + "/context", params=old, json={"question": "Explain original"})
    assert context.status_code == 200, context.text
    assert context.json()["snapshot_id"] == old["revision"]
    assert any("main evidence" in c["content"] for c in context.json()["evidence"])
    assert (
        client.get(base + "/conversations", params=old).json()[0]["snapshot_id"] == old["revision"]
    )
    assert client.get(base + "/conversations", params=feature).json() == []
    snapshots = client.get(base + "/snapshots").json()
    assert len(snapshots) == 2 and snapshots[0]["current"] and not snapshots[1]["current"]
    assert len(client.get(base + "/snapshots", params=feature).json()) == 1
    # The no-change scan reuses the snapshot instead of publishing fake revisions.
    client.post(base + "/jobs")
    run_once()
    assert len(client.get(base + "/snapshots").json()) == 2


def test_branch_and_snapshot_permissions(client, db, branch_repo):
    repo_id, _, _, owner = branch_repo
    base = f"/api/repositories/{repo_id}"
    revision = client.get(base).json()["snapshot_id"]
    outsider = register(client, "outsider@example.com")
    for endpoint in ["", "/branches", "/snapshots", "/graph", "/history", "/conversations"]:
        assert client.get(base + endpoint, params={"revision": revision}).status_code == 404
    assert client.post(base + "/branches", json={"branch": "secret"}).status_code == 404
    db.add(Membership(repository_id=repo_id, user_id=outsider["id"], permission="read"))
    db.commit()
    assert client.get(base + "/snapshots").status_code == 200
    assert client.post(base + "/branches", json={"branch": "secret"}).status_code == 403
    assert client.post(base + "/jobs").status_code == 403
    # A valid snapshot UUID from another repository must still be rejected.
    response = client.post(
        "/api/repositories/upload",
        files={"file": ("reference.zip", archive_bytes(), "application/zip")},
    )
    assert response.status_code == 201
    second = response.json()["repository"]["id"]
    run_once()
    second_snapshot = client.get(f"/api/repositories/{second}").json()["snapshot_id"]
    assert client.get(base, params={"revision": second_snapshot}).status_code == 404
    for snap in db.scalars(select(Snapshot).where(Snapshot.repository_id == second)):
        store.delete_graph(snap.graph_name)
    assert owner["id"] != outsider["id"]


def test_archive_branch_connection_rejected(client, db):
    repo_id = connected(client)
    response = client.post(f"/api/repositories/{repo_id}/branches", json={"branch": "feature"})
    assert response.status_code == 422
    store.delete_graph(db.get(Repository, repo_id).graph_name)


def test_branch_history_publish_and_partial_records_are_not_visible(
    client, db, branch_repo, monkeypatch
):
    repo_id, _, _, _ = branch_repo
    base = f"/api/repositories/{repo_id}"
    initial = client.get(base).json()
    client.post(base + "/branches", json={"branch": "feature/evidence"})
    run_once()
    branch = {"branch": "feature/evidence"}
    previous = client.get(base, params=branch).json()
    repo = db.get(Repository, repo_id)
    repo.source_type, repo.source = "github", "https://github.com/test/branch-fixture"
    db.commit()
    calls = []
    changes = {"body": "An issue", "fail": False}

    def get(self, path, params=None):
        self.requests += 1
        calls.append((path, params))
        if path.endswith("/issues"):
            return [
                {
                    "number": 12,
                    "title": "Branch evidence",
                    "body": changes["body"],
                    "state": "open",
                    "html_url": "https://github.com/test/branch-fixture/issues/12",
                    "updated_at": "2026-01-01T00:00:00Z",
                }
            ], False
        if path.endswith("/actions/runs"):
            return {"workflow_runs": []}, False
        if path.endswith("/pulls") and changes["fail"]:
            from api.ingestion.sources import SourceError

            raise SourceError("GitHub fixture interrupted after saving an issue page")
        return [], False

    monkeypatch.setattr(GitHub, "get", get)
    assert client.post(base + "/jobs?kind=github-sync&branch=feature%2Fevidence").status_code == 201
    run_once()
    assert client.get(base + "/jobs", params=branch).json()[0]["status"] == "succeeded"
    history = client.get(base + "/history", params=branch).json()
    assert history["items"][0]["number"] == 12
    assert client.get(base + "/history").json()["items"] == []
    assert client.get(base).json()["snapshot_id"] == initial["snapshot_id"]
    assert (
        client.get(base + "/history", params=branch | {"revision": previous["snapshot_id"]}).json()[
            "items"
        ]
        == []
    )
    assert any(path.endswith("/commits") and p["sha"] == "feature/evidence" for path, p in calls)
    assert any(
        path.endswith("/actions/runs") and p["branch"] == "feature/evidence" for path, p in calls
    )
    published = client.get(base, params=branch).json()
    changes.update(body="Not published yet", fail=True)
    client.post(base + "/jobs", params=branch | {"kind": "github-sync"})
    run_once()
    assert client.get(base + "/jobs", params=branch).json()[0]["status"] == "failed"
    assert client.get(base, params=branch).json()["snapshot_id"] == published["snapshot_id"]
    assert client.get(base + "/history", params=branch).json()["items"][0]["body"] == "An issue"
    # Source indexing must also ignore unpublished staging rows from that sync.
    from api.services import indexing

    original_snapshot = indexing.snapshot
    with monkeypatch.context() as local_source:
        local_source.setattr(
            indexing,
            "snapshot",
            lambda source_type, source, selected, tree: original_snapshot(
                "local", str(branch_repo[1]), selected, tree
            ),
        )
        client.post(base + "/jobs", params=branch)
        run_once()
    assert client.get(base + "/jobs", params=branch).json()[0]["status"] == "succeeded"
    assert client.get(base, params=branch).json()["stats"]["graph_writes"] == 0
    assert client.get(base + "/history", params=branch).json()["items"][0]["body"] == "An issue"
    changes["fail"] = False
    client.post(base + "/jobs", params=branch | {"kind": "github-sync"})
    run_once()
    assert (
        client.get(base + "/history", params=branch).json()["items"][0]["body"]
        == "Not published yet"
    )
    assert (
        client.get(
            base + "/history", params=branch | {"revision": published["snapshot_id"]}
        ).json()["items"][0]["body"]
        == "An issue"
    )
