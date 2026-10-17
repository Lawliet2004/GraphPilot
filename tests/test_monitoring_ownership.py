from datetime import timedelta

from sqlalchemy import select

from api.db import utcnow
from api.graph import store
from api.models import Audit, Job, Membership, Repository, User, WorkerHeartbeat
from api.services.telemetry import request_metrics
from api.worker import heartbeat, run_once
from tests.conftest import register
from tests.test_indexing import connected


def promote(db, user):
    db.get(User, user["id"]).role = "admin"
    db.commit()


def test_ownership_transfer_permissions_and_audit(client, db):
    repo_id = connected(client)
    base = f"/api/repositories/{repo_id}"
    owner_cookies = dict(client.cookies)
    owner_csrf = client.headers["X-CSRF-Token"]
    old_owner = db.get(Repository, repo_id).owner_id
    recipient = register(client, "recipient@example.com")
    recipient_cookies = dict(client.cookies)
    recipient_csrf = client.headers["X-CSRF-Token"]
    path = f"/api/admin/repositories/{repo_id}/ownership"
    body = {"new_owner_id": recipient["id"], "previous_owner_access": "remove"}
    assert client.post(path, json=body).status_code == 403
    actor = register(client, "admin@example.com")
    promote(db, actor)
    db.get(User, recipient["id"]).disabled = True
    db.commit()
    assert client.post(path, json=body).status_code == 409
    db.get(User, recipient["id"]).disabled = False
    db.commit()
    assert client.post(path, json=body).status_code == 200
    assert client.post(path, json=body).status_code == 409
    db.expire_all()
    assert db.get(Repository, repo_id).owner_id == recipient["id"]
    assert db.get(Membership, (repo_id, recipient["id"])).permission == "owner"
    assert db.get(Membership, (repo_id, old_owner)) is None
    assert client.get(base + "/graph").status_code == 404
    event = db.scalar(select(Audit).where(Audit.action == "admin.ownership_transferred"))
    assert (
        event.details["previous_owner_id"] == old_owner
        and event.details["new_owner_id"] == recipient["id"]
    )
    client.cookies.clear()
    client.cookies.update(owner_cookies)
    client.headers["X-CSRF-Token"] = owner_csrf
    assert client.get(base).status_code == 404
    client.cookies.clear()
    client.cookies.update(recipient_cookies)
    client.headers["X-CSRF-Token"] = recipient_csrf
    assert client.get(base).json()["permission"] == "owner"
    assert client.post(base + "/jobs").status_code == 201
    run_once()
    store.delete_graph(db.get(Repository, repo_id).graph_name)


def test_admin_cancels_and_retries_without_source_bypass(client, db):
    repo_id = connected(client)
    base = f"/api/repositories/{repo_id}"
    job = client.post(base + "/jobs").json()
    cancel = f"/api/admin/jobs/{job['id']}/cancel"
    assert client.post(cancel).status_code == 403
    actor = register(client, "admin@example.com")
    promote(db, actor)
    response = client.post(cancel)
    assert response.status_code == 200 and response.json()["status"] == "cancelled"
    assert client.post(cancel).status_code == 409
    retry = client.post(f"/api/admin/jobs/{job['id']}/retry")
    assert retry.status_code == 200 and retry.json()["branch"] == job["branch"]
    assert client.post(f"/api/admin/jobs/{job['id']}/retry").status_code == 409
    run_once()
    assert client.get(base + "/graph").status_code == 404
    db.expire_all()
    assert db.get(Job, retry.json()["id"]).status == "succeeded"
    assert db.scalar(select(Audit).where(Audit.action == "admin.job_cancel"))
    store.delete_graph(db.get(Repository, repo_id).graph_name)


def test_worker_observations_and_real_metrics_are_permission_checked(client, db):
    user = register(client)
    assert client.get("/api/admin/metrics").status_code == 403
    promote(db, user)
    heartbeat("test-worker")
    before = request_metrics()["requests_since_start"]
    result = client.get("/api/admin/metrics").json()
    assert result["postgres_bytes"] > 0
    assert result["requests"]["requests_since_start"] >= before
    assert result["workers"][0]["observation"] == "recent"
    row = db.get(WorkerHeartbeat, "test-worker")
    row.last_seen = utcnow() - timedelta(seconds=60)
    db.commit()
    assert client.get("/api/admin/metrics").json()["workers"][0]["observation"] == "stale"
    heartbeat("test-worker", stopped=True)
    assert client.get("/api/admin/metrics").json()["workers"][0]["observation"] == "stopped"
    db.expire_all()
    assert len(list(db.scalars(select(WorkerHeartbeat)))) == 1


def test_error_headers_and_metrics_do_not_leak_exception_text(client, db, monkeypatch, caplog):
    repo_id = connected(client)

    def fail(*args, **kwargs):
        raise RuntimeError("SECRET-ERROR-TEXT-SHOULD-NEVER-LEAK")

    before = request_metrics()["application_errors_since_start"]
    monkeypatch.setattr(store, "search", fail)
    response = client.get(f"/api/repositories/{repo_id}/search?q=normalize")
    assert response.status_code == 500
    assert (
        response.headers["x-content-type-options"] == "nosniff"
        and response.headers["cache-control"] == "no-store"
    )
    assert "SECRET-ERROR-TEXT" not in response.text and "SECRET-ERROR-TEXT" not in caplog.text
    assert request_metrics()["application_errors_since_start"] == before + 1
    store.delete_graph(db.get(Repository, repo_id).graph_name)
