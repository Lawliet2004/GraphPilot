from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from api.auth import admin, audit, public_user
from api.db import db_session, utcnow
from api.models import (
    Audit,
    Job,
    LoginSession,
    Membership,
    Repository,
    RepositoryBranch,
    RuntimeSetting,
    User,
    WorkerHeartbeat,
)
from api.routes.repositories import job_json, repository_json
from api.services.runtime_config import LogPolicy, clear_cache, read_policy
from api.services.telemetry import request_metrics, storage_metrics

router = APIRouter(prefix="/api/admin", tags=["administration"])


@router.get("/config")
def configuration(actor=Depends(admin), db: Session = Depends(db_session)):
    return {
        "values": read_policy(db),
        "application_delay_seconds": 5,
        "scope": "New CI log archives and downloads; existing archives retain their original expiration",
    }


@router.put("/config")
def configure(body: LogPolicy, actor=Depends(admin), db: Session = Depends(db_session)):
    before = read_policy(db)
    values = body.model_dump()
    for key, value in values.items():
        row = db.get(RuntimeSetting, key)
        if row is None:
            row = RuntimeSetting(key=key)
            db.add(row)
        row.value, row.updated_by, row.updated_at = value, actor.id, utcnow()
    audit(db, actor.id, "admin.configuration_updated", previous=before, current=values)
    db.commit()
    clear_cache()
    return {
        "values": values,
        "application_delay_seconds": 5,
        "scope": "New CI log archives and downloads; existing archives retain their original expiration",
    }


@router.get("/users")
def users(user=Depends(admin), db: Session = Depends(db_session)):
    return [public_user(u) for u in db.scalars(select(User).order_by(User.created_at).limit(500))]


class AccountUpdate(BaseModel):
    role: str | None = None
    disabled: bool | None = None


@router.patch("/users/{user_id}")
def update_user(
    user_id: str, body: AccountUpdate, actor=Depends(admin), db: Session = Depends(db_session)
):
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if not user:
        raise HTTPException(404, "Account not found")
    if body.role is not None and body.role not in {"user", "admin"}:
        raise HTTPException(422, "Choose user or admin role")
    if actor.id == user_id and (body.disabled or body.role == "user"):
        raise HTTPException(409, "You cannot disable or demote your own administrator account")
    previous = {"role": user.role, "disabled": user.disabled}
    if body.role is not None:
        user.role = body.role
    if body.disabled is not None:
        user.disabled = body.disabled
    if user.disabled:
        db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
    audit(
        db,
        actor.id,
        "admin.account_update",
        user.id,
        previous=previous,
        current={"role": user.role, "disabled": user.disabled},
    )
    db.commit()
    return public_user(user)


@router.get("/repositories")
def repositories(user=Depends(admin), db: Session = Depends(db_session)):
    # Administrative metadata only. Admins must explicitly grant themselves
    # membership (audited) before reading code, graph data or evidence.
    rows = db.scalars(select(Repository).order_by(Repository.created_at.desc()).limit(500))
    return [repository_json(r) | {"owner_id": r.owner_id} for r in rows]


@router.get("/repositories/{repository_id}/members")
def members(repository_id: str, user=Depends(admin), db: Session = Depends(db_session)):
    if not db.get(Repository, repository_id):
        raise HTTPException(404, "Repository not found")
    return [
        {"user_id": m.user_id, "permission": m.permission, "email": u.email}
        for m, u in db.execute(
            select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .where(Membership.repository_id == repository_id)
        )
    ]


class AccessUpdate(BaseModel):
    permission: str


@router.put("/repositories/{repository_id}/members/{user_id}")
def grant(
    repository_id: str,
    user_id: str,
    body: AccessUpdate,
    actor=Depends(admin),
    db: Session = Depends(db_session),
):
    if body.permission not in {"read", "write"}:
        raise HTTPException(422, "Choose read or write permission")
    repo, user = db.get(Repository, repository_id), db.get(User, user_id)
    if not repo or not user:
        raise HTTPException(404, "Repository or account not found")
    if user.id == repo.owner_id:
        raise HTTPException(409, "The repository owner keeps owner permission")
    member = db.get(Membership, (repository_id, user_id))
    if not member:
        member = Membership(repository_id=repository_id, user_id=user_id)
        db.add(member)
    member.permission = body.permission
    audit(
        db,
        actor.id,
        "admin.access_granted",
        repository_id,
        member_id=user_id,
        permission=body.permission,
    )
    db.commit()
    return {"user_id": user_id, "permission": body.permission}


@router.delete("/repositories/{repository_id}/members/{user_id}")
def revoke(
    repository_id: str, user_id: str, actor=Depends(admin), db: Session = Depends(db_session)
):
    repo = db.get(Repository, repository_id)
    member = db.get(Membership, (repository_id, user_id))
    if not repo or not member:
        raise HTTPException(404, "Membership not found")
    if user_id == repo.owner_id:
        raise HTTPException(409, "Cannot revoke the repository owner")
    db.delete(member)
    audit(db, actor.id, "admin.access_revoked", repository_id, member_id=user_id)
    db.commit()
    return {"message": "Repository access revoked"}


class OwnershipTransfer(BaseModel):
    new_owner_id: str
    previous_owner_access: Literal["read", "write", "remove"]


@router.post("/repositories/{repository_id}/ownership")
def transfer_ownership(
    repository_id: str,
    body: OwnershipTransfer,
    actor=Depends(admin),
    db: Session = Depends(db_session),
):
    repo = db.scalar(select(Repository).where(Repository.id == repository_id).with_for_update())
    user = db.get(User, body.new_owner_id)
    if not repo or not user:
        raise HTTPException(404, "Repository or account not found")
    if user.disabled:
        raise HTTPException(409, "Enable the receiving account before transferring ownership")
    if user.id == repo.owner_id:
        raise HTTPException(409, "This account already owns the repository")
    previous = repo.owner_id
    old = db.get(Membership, (repo.id, previous))
    if old:
        if body.previous_owner_access == "remove":
            db.delete(old)
        else:
            old.permission = body.previous_owner_access
    new = db.get(Membership, (repo.id, user.id))
    if new is None:
        new = Membership(repository_id=repo.id, user_id=user.id)
        db.add(new)
    new.permission = "owner"
    repo.owner_id = user.id
    audit(
        db,
        actor.id,
        "admin.ownership_transferred",
        repo.id,
        previous_owner_id=previous,
        new_owner_id=user.id,
        previous_owner_access=body.previous_owner_access,
    )
    db.commit()
    return {
        "repository_id": repo.id,
        "owner_id": user.id,
        "previous_owner_access": body.previous_owner_access,
    }


@router.get("/jobs")
def jobs(user=Depends(admin), db: Session = Depends(db_session)):
    return [job_json(j) for j in db.scalars(select(Job).order_by(Job.created_at.desc()).limit(100))]


@router.post("/jobs/{job_id}/retry")
def retry(job_id: str, actor=Depends(admin), db: Session = Depends(db_session)):
    job = db.get(Job, job_id)
    if not job or job.status not in {"failed", "cancelled"}:
        raise HTTPException(409, "Only failed or cancelled jobs can be retried")
    repo = db.get(Repository, job.repository_id)
    db.refresh(repo, with_for_update=True)
    if repo.status == "deleting" and job.kind != "delete":
        raise HTTPException(409, "Repository removal is in progress")
    if db.scalar(
        select(Job).where(Job.repository_id == repo.id, Job.status.in_(["queued", "running"]))
    ):
        raise HTTPException(409, "Repository already has an active job")
    new = Job(
        repository_id=job.repository_id, requested_by=actor.id, kind=job.kind, branch=job.branch
    )
    db.add(new)
    db.flush()
    audit(db, actor.id, "admin.job_retry", new.id, previous_job=job.id)
    db.commit()
    return job_json(new)


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, actor=Depends(admin), db: Session = Depends(db_session)):
    job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
    if not job:
        raise HTTPException(404, "Job not found")
    if job.kind == "delete":
        raise HTTPException(409, "Repository removal cannot be cancelled after confirmation")
    if job.status not in {"queued", "running"}:
        raise HTTPException(409, "Only active jobs can be cancelled")
    job.cancel_requested = True
    if job.status == "queued":
        job.status, job.message, job.finished_at = (
            "cancelled",
            "Cancelled before execution",
            utcnow(),
        )
    audit(db, actor.id, "admin.job_cancel", job.id, repository_id=job.repository_id)
    db.commit()
    return job_json(job)


@router.get("/audit")
def audits(
    limit: int = Query(100, ge=1, le=500), user=Depends(admin), db: Session = Depends(db_session)
):
    return [
        {
            "id": a.id,
            "user_id": a.user_id,
            "action": a.action,
            "target": a.target,
            "details": a.details,
            "created_at": a.created_at,
        }
        for a in db.scalars(select(Audit).order_by(Audit.created_at.desc()).limit(limit))
    ]


@router.get("/metrics")
def metrics(user=Depends(admin), db: Session = Depends(db_session)):
    def count(model):
        return db.scalar(select(func.count()).select_from(model))

    repos = list(db.scalars(select(Repository)))
    branches = list(
        db.scalars(
            select(RepositoryBranch)
            .join(Repository)
            .where(RepositoryBranch.branch != Repository.branch)
        )
    )
    workers = [
        {
            "worker_id": w.worker_id,
            "status": w.status,
            "active_job_id": w.active_job_id,
            "last_seen": w.last_seen,
            "observation": "stopped"
            if w.status == "stopped"
            else "recent"
            if w.last_seen > utcnow() - timedelta(seconds=45)
            else "stale",
        }
        for w in db.scalars(
            select(WorkerHeartbeat).order_by(WorkerHeartbeat.last_seen.desc()).limit(50)
        )
    ]
    return {
        "users": count(User),
        "repositories": len(repos),
        "graph_entities": sum(r.stats.get("nodes", 0) for r in [*repos, *branches]),
        "jobs": count(Job),
        "failed_jobs": db.scalar(
            select(func.count()).select_from(Job).where(Job.status == "failed")
        ),
        "active_sessions": db.scalar(
            select(func.count()).select_from(LoginSession).where(LoginSession.expires_at > utcnow())
        ),
        "graph_counts_scope": "Latest published snapshot per connected repository/branch; excludes older generations",
        "requests": request_metrics(),
        "artifacts": storage_metrics(),
        "workers": workers,
        "postgres_bytes": db.scalar(select(func.pg_database_size(func.current_database()))),
    }
