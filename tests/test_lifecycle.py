"""Actual owned storage removal, failure recovery, read locks and retention."""

import hashlib
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from api.config import settings
from api.db import engine, utcnow
from api.graph import store
from api.models import Audit, Conversation, Job, Membership, Repository, Snapshot
from api.services.lifecycle import prune_snapshots, storage_read_lock
from api.services.revisions import publish_snapshot
from api.worker import run_once
from tests.conftest import register
from tests.test_indexing import connected


def test_local_repository_removal_preserves_authoritative_directory(client, db, tmp_path):
    repo_id = connected(client)
    source = tmp_path / "authoritative-git"
    source.mkdir()
    (source / "keep.py").write_text("authoritative code")
    repo = db.get(Repository, repo_id)
    uploaded_input = Path(repo.source)
    repo.source_type, repo.source = "local", str(source)
    db.commit()
    assert (
        client.request(
            "DELETE", f"/api/repositories/{repo_id}", json={"confirm_name": repo.name}
        ).status_code
        == 202
    )
    assert run_once()
    assert (source / "keep.py").read_text() == "authoritative code"
    uploaded_input.unlink(missing_ok=True)  # No longer associated after fixture source replacement.


def test_owner_removal_is_durable_scoped_and_retryable(client, db, monkeypatch, tmp_path):
    repo_id = connected(client)
    repo = db.get(Repository, repo_id)
    name, graph, source = repo.name, repo.graph_name, repo.source
    source_path = Path(source)
    snapshot_root = settings().data_dir.resolve() / "snapshots" / repo_id
    unrelated = tmp_path / "server-local-repository"
    unrelated.mkdir()
    (unrelated / "keep.py").write_text("never remove unrelated data")
    outsider = register(client, "removal-outsider@example.com")
    base = f"/api/repositories/{repo_id}"
    assert client.request("DELETE", base, json={"confirm_name": name}).status_code == 404
    db.add(Membership(repository_id=repo_id, user_id=outsider["id"], permission="write"))
    db.commit()
    assert client.request("DELETE", base, json={"confirm_name": name}).status_code == 403
    # Recover the owner's existing account through real login.
    response = client.post(
        "/api/auth/login",
        json={"email": "dev@example.com", "password": "correct-horse-battery"},
    )
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = response.json()["csrf"]
    assert client.request("DELETE", base, json={"confirm_name": "wrong"}).status_code == 422
    queued = client.request("DELETE", base, json={"confirm_name": name})
    assert queued.status_code == 202, queued.text
    assert queued.json()["kind"] == "delete"
    assert client.get(base + "/graph").status_code == 404
    assert client.get("/api/repositories").json() == []
    assert client.post(base + "/jobs").status_code == 404
    from api.services import lifecycle

    original_remove = lifecycle.remove_owned_directory

    def interrupted(*args, **kwargs):
        raise OSError("Synthetic storage outage")

    with monkeypatch.context() as fail:
        fail.setattr(lifecycle, "remove_owned_directory", interrupted)
        assert run_once()
    db.expire_all()
    assert db.get(Job, queued.json()["id"]).status == "failed"
    assert db.get(Repository, repo_id).status == "deleting"
    assert source_path.exists() and snapshot_root.exists()
    assert graph not in store.client().list_graphs()
    monkeypatch.setattr(lifecycle, "remove_owned_directory", original_remove)
    assert client.request("DELETE", base, json={"confirm_name": name}).status_code == 202
    assert run_once()
    db.expire_all()
    assert db.get(Repository, repo_id) is None
    assert db.scalar(select(Job.id).where(Job.repository_id == repo_id)) is None
    assert db.scalar(select(Snapshot.id).where(Snapshot.repository_id == repo_id)) is None
    assert not source_path.exists() and not snapshot_root.exists()
    assert (unrelated / "keep.py").read_text() == "never remove unrelated data"
    assert db.scalar(
        select(Audit).where(Audit.action == "repository.removed", Audit.target == repo_id)
    )
    assert client.get(base).status_code == 404


def test_retirement_preserves_heads_pins_shared_sources_and_recovers_cleanup(
    client, db, monkeypatch
):
    repo_id = connected(client)
    repo = db.get(Repository, repo_id)
    root = settings().data_dir.resolve() / "snapshots" / repo_id
    first = db.scalar(select(Snapshot).where(Snapshot.repository_id == repo_id))
    original_stats = dict(repo.stats)
    client.post(f"/api/repositories/{repo_id}/context", json={"question": "normalize"})
    assert db.scalar(select(Conversation.snapshot_id)) == first.id
    graphs = [repo.graph_name]
    snapshots = [first]
    unique_tree = hashlib.sha256(b"synthetic retention-only source artifact").hexdigest()
    (root / unique_tree).mkdir()
    (root / unique_tree / "retention.txt").write_text("retired fixture")
    for index in range(3):
        graph = store.graph_name(repo_id, repo.branch, f"retention-fixture-{index}")
        store.copy_snapshot(repo.graph_name, graph)
        stats = {
            **original_stats,
            "tree_hash": unique_tree if index == 1 else original_stats["tree_hash"],
        }
        snapshots.append(
            publish_snapshot(db, repo, repo.branch, "index", graph, repo.commit_sha, stats, {})
        )
        db.commit()
        graphs.append(graph)
    for snapshot in snapshots[:-1]:
        snapshot.created_at = utcnow() - timedelta(days=40)
    db.commit()
    monkeypatch.setattr(settings(), "snapshot_keep_per_branch", 1)
    monkeypatch.setattr(settings(), "snapshot_retention_days", 30)
    try:
        # Active evidence readers defer maintenance instead of losing their files.
        with engine.connect() as reader:
            storage_read_lock(reader, repo_id)
            assert prune_snapshots(repo_id)["deferred"]
            reader.rollback()
        original_delete = store.delete_graph
        with monkeypatch.context() as outage:

            def fail(*args):
                raise RuntimeError("Synthetic graph outage")

            outage.setattr(store, "delete_graph", fail)
            with pytest.raises(RuntimeError):
                prune_snapshots(repo_id)
        db.expire_all()
        assert db.get(Snapshot, snapshots[1].id).retired_at is not None
        assert db.get(Snapshot, snapshots[1].id).purged_at is None
        assert (
            client.get(
                f"/api/repositories/{repo_id}", params={"revision": snapshots[1].id}
            ).status_code
            == 410
        )
        assert prune_snapshots(repo_id) == {"retired": 0, "purged": 2, "deferred": False}
        assert prune_snapshots(repo_id) == {"retired": 0, "purged": 0, "deferred": False}
        assert (root / original_stats["tree_hash"]).is_dir()
        assert not (root / unique_tree).exists()
        assert set(graphs[:1] + graphs[-1:]) <= set(store.client().list_graphs())
        assert not set(graphs[1:3]) & set(store.client().list_graphs())
        assert (
            client.get(f"/api/repositories/{repo_id}", params={"revision": first.id}).status_code
            == 200
        )
        assert len(client.get(f"/api/repositories/{repo_id}/snapshots").json()) == 2
    finally:
        for graph in graphs:
            original_delete(graph)
