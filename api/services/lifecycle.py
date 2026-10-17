"""Owned-data deletion and resumable snapshot retirement.

Storage read locks protect in-flight evidence requests. Worker repository locks
serialize destructive maintenance with indexing; no submitted source code runs.
"""

import hashlib
import logging
import re
import shutil
import uuid
from datetime import timedelta
from pathlib import Path

from sqlalchemy import delete, func, select, text

from api.auth import audit
from api.config import settings
from api.db import SessionLocal, utcnow
from api.graph import store
from api.ingestion.sources import SourceError
from api.models import Conversation, Job, Repository, RepositoryBranch, Snapshot

log = logging.getLogger("graphpilot.lifecycle")


def discard_unpublished(repository_id, graph_name, fingerprint=None):
    """A lost commit acknowledgement must never destroy a published generation.

    If publication status cannot be checked, keep artifacts for later owned
    cleanup rather than treating an uncertain distributed write as a rollback.
    """
    try:
        with SessionLocal() as db:
            if db.scalar(select(Snapshot.id).where(Snapshot.graph_name == graph_name).limit(1)):
                return
            prefix = "gp_" + str(uuid.UUID(repository_id)).replace("-", "") + "_"
            if not graph_name.startswith(prefix):
                raise SourceError("Unpublished graph is outside its owned namespace")
            store.delete_graph(graph_name)
            if fingerprint and not db.scalar(
                select(Snapshot.id)
                .where(
                    Snapshot.repository_id == repository_id,
                    Snapshot.retired_at.is_(None),
                    Snapshot.stats["tree_hash"].as_string() == fingerprint,
                )
                .limit(1)
            ):
                remove_owned_directory("snapshots", repository_id, fingerprint)
    except Exception as exc:
        log.warning("event=unpublished_cleanup_deferred error_type=%s", type(exc).__name__)


def storage_key(repository_id):
    return int.from_bytes(
        hashlib.sha256(("graphpilot-storage:" + repository_id).encode()).digest()[:8], signed=True
    )


def storage_read_lock(db, repository_id):
    db.execute(
        text("SELECT pg_advisory_xact_lock_shared(:key)"), {"key": storage_key(repository_id)}
    )


def remove_owned_directory(category, repository_id, child=None):
    repository_id = str(uuid.UUID(repository_id))
    root = settings().data_dir.resolve() / category
    if root.is_symlink():
        raise SourceError("Artifact storage root must not be a symbolic link")
    path = root / repository_id
    if child is not None:
        if not re.fullmatch(r"[a-f0-9]{64}", child) or path.is_symlink():
            raise SourceError("Invalid owned snapshot path")
        path /= child
    if path.is_symlink():
        path.unlink()  # Never follow a link into a submitted or unrelated directory.
    elif path.exists():
        if not path.resolve().is_relative_to(root.resolve()):
            raise SourceError("Artifact path escaped owned storage")
        shutil.rmtree(path)


def delete_repository(job_id, worker_id):
    with SessionLocal() as db:
        job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
        if not job or job.worker_id != worker_id or job.status != "running":
            raise SourceError("Removal job no longer belongs to this worker")
        repo = db.get(Repository, job.repository_id)
        if repo.status != "deleting":
            raise SourceError("Repository removal has not been requested")
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": storage_key(repo.id)})
        prefix = "gp_" + str(uuid.UUID(repo.id)).replace("-", "") + "_"
        # Includes unpublished leftovers belonging to this UUID, never display names.
        for name in store.client().list_graphs():
            if name.startswith(prefix):
                store.delete_graph(name)
        remove_owned_directory("snapshots", repo.id)
        remove_owned_directory("logs", repo.id)
        if repo.source_type == "archive":
            source = Path(repo.source)
            uploads = settings().data_dir.resolve() / "uploads"
            if (
                uploads.is_symlink()
                or source.parent != uploads
                or not re.fullmatch(r"[a-f0-9-]{36}\.zip", source.name)
            ):
                raise SourceError(
                    "Uploaded input is outside owned storage; administrator review required"
                )
            source.unlink(missing_ok=True)
        # Work directories are keyed by durable job UUIDs, not submitted paths.
        for identifier in db.scalars(select(Job.id).where(Job.repository_id == repo.id)):
            remove_owned_directory("work", identifier)
        audit(db, job.requested_by, "repository.removed", repo.id, job_id=job.id)
        db.execute(delete(Repository).where(Repository.id == repo.id))
        db.commit()


def prune_snapshots(repository_id):
    cfg = settings()
    with SessionLocal() as db:
        repo_key = int(uuid.UUID(repository_id)) % (2**63 - 1)
        if not db.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": repo_key}):
            return {"retired": 0, "purged": 0, "deferred": True}
        repo = db.get(Repository, repository_id)
        if not repo or repo.status == "deleting":
            return {"retired": 0, "purged": 0, "deferred": True}
        if not db.scalar(
            text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": storage_key(repo.id)}
        ):
            return {"retired": 0, "purged": 0, "deferred": True}
        heads = {repo.graph_name} | set(
            db.scalars(
                select(RepositoryBranch.graph_name).where(RepositoryBranch.repository_id == repo.id)
            )
        )
        ranked = (
            select(
                Snapshot.id,
                func.row_number()
                .over(
                    partition_by=Snapshot.branch, order_by=(Snapshot.created_at.desc(), Snapshot.id)
                )
                .label("position"),
            )
            .where(Snapshot.repository_id == repo.id, Snapshot.retired_at.is_(None))
            .subquery()
        )
        pins = select(Conversation.snapshot_id).where(
            Conversation.repository_id == repo.id, Conversation.snapshot_id.is_not(None)
        )
        candidates = db.scalars(
            select(Snapshot)
            .join(ranked, ranked.c.id == Snapshot.id)
            .where(
                ranked.c.position > cfg.snapshot_keep_per_branch,
                Snapshot.created_at < utcnow() - timedelta(days=cfg.snapshot_retention_days),
                Snapshot.graph_name.not_in([h for h in heads if h]),
                Snapshot.id.not_in(pins),
            )
            .order_by(Snapshot.created_at)
            .limit(100)
        ).all()
        for snapshot in candidates:
            snapshot.retired_at = utcnow()
        if candidates:
            audit(db, None, "system.snapshots_retired", repo.id, count=len(candidates))
        db.commit()  # Retirement is durable before any irreversible storage operation.
    purged = 0
    with SessionLocal() as db:
        if not db.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": repo_key}):
            return {"retired": len(candidates), "purged": 0, "deferred": True}
        if not db.scalar(
            text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": storage_key(repository_id)}
        ):
            return {"retired": len(candidates), "purged": 0, "deferred": True}
        rows = db.scalars(
            select(Snapshot)
            .where(
                Snapshot.repository_id == repository_id,
                Snapshot.retired_at.is_not(None),
                Snapshot.purged_at.is_(None),
            )
            .limit(100)
        ).all()
        for snapshot in rows:
            prefix = "gp_" + repository_id.replace("-", "") + "_"
            if not snapshot.graph_name.startswith(prefix):
                raise SourceError("Snapshot graph is outside its owned namespace")
            store.delete_graph(snapshot.graph_name)
            fingerprint = snapshot.stats.get("tree_hash")
            if fingerprint:
                referenced = db.scalar(
                    select(Snapshot.id)
                    .where(
                        Snapshot.repository_id == repository_id,
                        Snapshot.retired_at.is_(None),
                        Snapshot.stats["tree_hash"].as_string() == fingerprint,
                    )
                    .limit(1)
                )
                if not referenced:
                    remove_owned_directory("snapshots", repository_id, fingerprint)
            snapshot.purged_at = utcnow()
            purged += 1
        if purged:
            audit(db, None, "system.snapshots_purged", repository_id, count=purged)
        db.commit()
    return {"retired": len(candidates), "purged": purged, "deferred": False}
