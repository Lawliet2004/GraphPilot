from fastapi import HTTPException
from sqlalchemy.orm import Session

from api.models import Membership, Repository, User


def repository_access(
    db: Session, user: User, repository_id: str, write=False, allow_deleting=False
) -> Repository:
    from api.services.lifecycle import storage_read_lock

    storage_read_lock(db, repository_id)
    repo = db.get(Repository, repository_id)
    member = db.get(Membership, (repository_id, user.id))
    # Admin role does not silently bypass repository membership.
    if not repo or not member or repo.status == "deleting" and not allow_deleting:
        raise HTTPException(404, "Repository not found")
    if write and member.permission not in {"write", "owner"}:
        raise HTTPException(403, "Repository write access required")
    return repo


def indexed(repo: Repository):
    if not repo.graph_name:
        raise HTTPException(409, "This repository has no successful index yet")
    return repo.graph_name
