"""Durable PostgreSQL worker with leased claims, advisory locks and fencing."""

import argparse
import logging
import signal
import threading
import time
import uuid
from datetime import timedelta

from sqlalchemy import or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from api.db import SessionLocal, engine, utcnow
from api.models import Job, Repository, WorkerHeartbeat
from api.services.indexing import JobCancelled, run_index
from api.services.revisions import state_for_branch

log = logging.getLogger("graphpilot.worker")
stop = False


def heartbeat(worker_id, stopped=False):
    with SessionLocal() as db:
        active = (
            None
            if stopped
            else db.scalar(
                select(Job.id).where(Job.worker_id == worker_id, Job.status == "running").limit(1)
            )
        )
        values = {
            "worker_id": worker_id,
            "last_seen": utcnow(),
            "status": "stopped" if stopped else "working" if active else "waiting",
            "active_job_id": active,
        }
        db.execute(
            insert(WorkerHeartbeat)
            .values(**values)
            .on_conflict_do_update(index_elements=[WorkerHeartbeat.worker_id], set_=values)
        )
        db.commit()


def heartbeat_loop(worker_id, done):
    while not done.is_set():
        try:
            heartbeat(worker_id)
        except SQLAlchemyError as exc:
            log.warning("event=worker_heartbeat_unavailable error_type=%s", type(exc).__name__)
        done.wait(10)


def claim_job(worker_id):
    with SessionLocal() as db:
        jobs = db.scalars(
            select(Job)
            .where(
                or_(
                    (Job.status == "queued") & (Job.available_at <= utcnow()),
                    (Job.status == "running") & (Job.lease_until < utcnow()),
                )
            )
            .order_by(Job.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        ).all()
        if not jobs:
            return None
        job = jobs[0]
        if job.cancel_requested or job.attempts >= 3:
            job.status = "cancelled" if job.cancel_requested else "failed"
            job.message = (
                "Cancelled"
                if job.cancel_requested
                else "Worker lease expired after maximum attempts"
            )
            job.finished_at = utcnow()
            db.commit()
            return None
        job.status, job.worker_id, job.attempts = "running", worker_id, job.attempts + 1
        # Each individual operation has a timeout shorter than this lease.
        from api.config import settings

        job.lease_until = utcnow() + timedelta(seconds=settings().job_timeout_seconds + 60)
        job.message = "Worker started"
        repo = db.get(Repository, job.repository_id)
        state_for_branch(db, repo, job.branch or repo.branch, create=True).status = (
            "indexing" if job.kind == "index" else "deleting" if job.kind == "delete" else "syncing"
        )
        db.commit()
        return job.id, job.repository_id, job.kind


def run_once(worker_id=None):
    worker_id = worker_id or str(uuid.uuid4())
    claimed = claim_job(worker_id)
    if not claimed:
        return False
    job_id, repo_id, kind = claimed
    # An advisory lock serializes jobs across workers and is released on disconnect.
    key = int(uuid.UUID(repo_id)) % (2**63 - 1)
    with engine.connect() as lock:
        acquired = lock.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": key})
        lock.commit()
        if not acquired:
            with SessionLocal() as db:
                job = db.get(Job, job_id)
                job.status, job.worker_id = "queued", None
                job.available_at = utcnow() + timedelta(seconds=2)
                job.attempts -= 1
                db.commit()
            return True
        try:
            if kind == "index":
                run_index(job_id, worker_id)
            elif kind == "github-sync":
                from api.services.github import run_sync

                run_sync(job_id, worker_id)
            elif kind == "delete":
                from api.services.lifecycle import delete_repository

                delete_repository(job_id, worker_id)
            else:
                raise ValueError("Unknown job type")
        except Exception as exc:
            log.warning("event=job_failed job_id=%s error_type=%s", job_id, type(exc).__name__)
            with SessionLocal() as db:
                job = db.get(Job, job_id)
                if job and job.worker_id == worker_id and job.status == "running":
                    job.status = "cancelled" if isinstance(exc, JobCancelled) else "failed"
                    # External exception text could contain secrets; publish only safe known messages.
                    from api.ingestion.sources import SourceError

                    job.message = (
                        "Cancelled at a safe checkpoint"
                        if isinstance(exc, JobCancelled)
                        else str(exc)
                        if isinstance(exc, SourceError)
                        else "Indexing failed. Administrator diagnostics are required."
                    )
                    from api.services.github import RateLimited

                    if isinstance(exc, RateLimited) and job.attempts < 3:
                        job.status = "queued"
                        job.available_at = utcnow() + timedelta(seconds=exc.seconds)
                        job.worker_id = None
                    job.finished_at = utcnow() if job.status in {"failed", "cancelled"} else None
                    repo = db.get(Repository, repo_id)
                    state = state_for_branch(db, repo, job.branch or repo.branch, create=True)
                    state.status = (
                        "deleting"
                        if kind == "delete"
                        else "ready"
                        if state.graph_name
                        else "failed"
                    )
                    db.commit()
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
            lock.commit()
    if kind in {"index", "github-sync"}:
        try:
            from api.services.lifecycle import prune_snapshots

            prune_snapshots(repo_id)
        except Exception as exc:
            log.warning("event=snapshot_cleanup_deferred error_type=%s", type(exc).__name__)
    return True


def main():
    global stop
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    def shutdown(*_):
        global stop
        stop = True

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    worker_id = str(uuid.uuid4())
    log.info("event=worker_start worker_id=%s", worker_id)
    done = threading.Event()
    pulse = threading.Thread(target=heartbeat_loop, args=(worker_id, done), daemon=True)
    pulse.start()
    next_cleanup = 0
    try:
        while not stop:
            try:
                if time.monotonic() >= next_cleanup:
                    from api.services.artifacts import purge_expired_logs

                    purge_expired_logs()
                    next_cleanup = time.monotonic() + 60
                worked = run_once(worker_id)
            except SQLAlchemyError as exc:
                log.warning("event=worker_database_unavailable error_type=%s", type(exc).__name__)
                engine.dispose()
                if args.once:
                    raise
                time.sleep(2)
                continue
            if args.once:
                break
            if not worked:
                time.sleep(1)
    finally:
        done.set()
        pulse.join(timeout=3)
        try:
            heartbeat(worker_id, stopped=True)
        except SQLAlchemyError:
            log.warning("event=worker_stop_heartbeat_unavailable")
        engine.dispose()


if __name__ == "__main__":
    main()
