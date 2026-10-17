"""Development-only restart drill for the owned native PostgreSQL and worker."""

import io
import json
import os
import secrets
import shutil
import subprocess
import time
import uuid
import zipfile
from pathlib import Path

import httpx
import psutil
from sqlalchemy import delete

from api.auth import password_hasher
from api.config import settings
from api.db import SessionLocal, engine
from api.graph import store
from api.models import Job, Repository, User
from scripts.maintenance import assert_no_browser_tests

root = Path.cwd()
assert_no_browser_tests(root)
assert settings().environment == "development" and engine.url.port == 55432
with SessionLocal() as db:
    from sqlalchemy import select

    assert not db.scalar(select(Job.id).where(Job.status.in_(["queued", "running"])).limit(1)), (
        "Wait for active jobs before the outage drill"
    )
worker = next(
    p
    for p in psutil.process_iter(["cmdline"])
    if p.info["cmdline"] == [str(root / ".venv/bin/python"), "-m", "api.worker"]
)
worker_pid = worker.pid
pg_bin = root / ".tools/postgres/usr/lib/postgresql/18/bin/pg_ctl"
env = {**os.environ, "LD_LIBRARY_PATH": str(root / ".tools/postgres/usr/lib/x86_64-linux-gnu")}
command = [str(pg_bin), "-D", str(root / ".data/postgres")]
repo_id = user_id = None
archive = root / ".data/recovery-fixture.zip"
report = {}
try:
    subprocess.run([*command, "-m", "fast", "-w", "stop"], env=env, check=True, capture_output=True)
    try:
        time.sleep(3)
        assert worker.is_running(), "Worker exited during database outage"
    finally:
        subprocess.run(
            [
                *command,
                "-l",
                str(root / ".data/postgres.log"),
                "-o",
                f"-p 55432 -h 127.0.0.1 -k {root}/.data/run -c max_connections=40 -c shared_buffers=64MB",
                "-w",
                "start",
            ],
            env=env,
            check=True,
            capture_output=True,
        )
    for _ in range(30):
        if httpx.get("http://127.0.0.1:8000/api/health/ready", timeout=5).status_code == 200:
            break
        time.sleep(0.2)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as zf:
        for path in Path("fixtures/reference").iterdir():
            if path.is_file():
                zf.write(path, path.name)
    archive.write_bytes(output.getvalue())
    with SessionLocal() as db:
        user = User(
            email=f"recovery-{uuid.uuid4()}@graphpilot.invalid",
            name="Disposable recovery probe",
            disabled=True,
            password_hash=password_hasher.hash(secrets.token_urlsafe(20)),
        )
        db.add(user)
        db.flush()
        user_id = user.id
        repo = Repository(
            name="Recovery fixture",
            owner_id=user.id,
            source_type="archive",
            source=str(archive),
            branch="recovery",
        )
        db.add(repo)
        db.flush()
        repo_id = repo.id
        job = Job(repository_id=repo.id, requested_by=user.id)
        db.add(job)
        db.commit()
        job_id = job.id
    for _ in range(60):
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            status = job.status
            message = job.message
        if status in {"succeeded", "failed"}:
            break
        time.sleep(0.2)
    assert status == "succeeded", message
    assert worker.is_running() and worker.pid == worker_pid
    report = {
        "status": "passed",
        "database_outage_seconds": 3,
        "worker_pid_unchanged": True,
        "post_recovery_index_job": "succeeded",
        "runtime": "Native PostgreSQL and external worker; not a container restart test.",
    }
finally:
    if repo_id:
        for name in store.client().list_graphs():
            if name.startswith("gp_" + repo_id.replace("-", "") + "_"):
                store.delete_graph(name)
        shutil.rmtree(settings().data_dir.resolve() / "snapshots" / repo_id, ignore_errors=True)
    with SessionLocal() as db:
        if repo_id:
            db.execute(delete(Repository).where(Repository.id == repo_id))
        if user_id:
            db.execute(delete(User).where(User.id == user_id))
        db.commit()
    archive.unlink(missing_ok=True)
    if report:
        Path("docs/WORKER_RECOVERY.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
