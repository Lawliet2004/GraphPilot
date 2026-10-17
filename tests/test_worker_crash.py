"""A killed real worker connection releases its lock; durable leases fence recovery."""

import selectors
import subprocess
import sys
from datetime import timedelta

import pytest

from api.db import utcnow
from api.graph import store
from api.models import Job, Repository
from api.services.indexing import JobCancelled, checkpoint
from api.worker import claim_job, run_once
from tests.conftest import register
from tests.test_indexing import archive_bytes


def test_process_crash_recovers_expired_claim_and_rejects_stale_worker(client, db):
    register(client)
    response = client.post(
        "/api/repositories/upload",
        files={"file": ("crash.zip", archive_bytes(), "application/zip")},
    )
    assert response.status_code == 201
    repo_id, job_id = response.json()["repository"]["id"], response.json()["job"]["id"]
    script = """
import time, uuid
from sqlalchemy import text
from api.worker import claim_job
from api.db import engine
claimed = claim_job("crashed-worker")
assert claimed is not None
with engine.connect() as connection:
 connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key":int(uuid.UUID(claimed[1])) % (2**63-1)})
 connection.commit()
 print("claimed", flush=True)
 time.sleep(60)
"""
    child = subprocess.Popen(
        [sys.executable, "-c", script], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
    )
    try:
        with selectors.DefaultSelector() as ready:
            ready.register(child.stdout, selectors.EVENT_READ)
            assert ready.select(timeout=10), "Disposable worker did not claim its fixture job"
            assert child.stdout.readline().strip() == "claimed"
        assert claim_job("second-worker") is None  # A live lease cannot be stolen.
        child.kill()
        child.wait(timeout=5)
        db.expire_all()
        job = db.get(Job, job_id)
        assert job.status == "running" and job.attempts == 1
        job.lease_until = utcnow() - timedelta(seconds=1)
        db.commit()
        assert run_once("recovered-worker")
        db.expire_all()
        job = db.get(Job, job_id)
        assert job.status == "succeeded" and job.attempts == 2
        assert job.worker_id == "recovered-worker"
        with pytest.raises(JobCancelled):
            checkpoint(job_id, "crashed-worker", 95, "Stale publication must fail")
        repo = db.get(Repository, repo_id)
        assert repo.stats["files"] == 4 and store.search(repo.graph_name, "normalize")
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)
        child.stdout.close()
        db.expire_all()
        repo = db.get(Repository, repo_id)
        if repo and repo.graph_name:
            store.delete_graph(repo.graph_name)
