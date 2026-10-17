"""Request-local branch/revision views. Reading never mutates the shared repository."""

import hashlib
import json
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.auth import current_session
from api.db import db_session, utcnow
from api.models import Membership, RepositoryBranch, Snapshot, User
from api.services.permissions import repository_access


@dataclass(frozen=True)
class RepositoryView:
    id: str
    name: str
    source_type: str
    source: str
    branch: str
    status: str
    commit_sha: str | None
    graph_name: str | None
    stats: dict
    sync_state: dict
    indexed_at: object
    created_at: object
    snapshot_id: str | None
    historical: bool
    permission: str


def state_for_branch(db, repo, branch, create=False):
    # Repository fields remain the canonical default-branch head, preserving
    # existing metadata and administrative queries. Other branches have own rows.
    if branch == repo.branch:
        return repo
    state = db.get(RepositoryBranch, (repo.id, branch))
    if state is None and create:
        state = RepositoryBranch(
            repository_id=repo.id, branch=branch, stats={}, sync_state={}, status="pending"
        )
        db.add(state)
        db.flush()
    if state is None:
        raise HTTPException(404, "Branch has not been connected to this repository")
    return state


def view_repository(db, user, repository_id, branch=None, revision=None):
    repo = repository_access(db, user, repository_id)
    selected = branch or repo.branch
    state = state_for_branch(db, repo, selected)
    snap = None
    if revision:
        snap = db.get(Snapshot, revision)
        if not snap or snap.repository_id != repo.id or snap.branch != selected:
            raise HTTPException(404, "Snapshot not found in this repository and branch")
        if snap.retired_at:
            raise HTTPException(
                410, "Snapshot retention has expired; this graph and source are unavailable"
            )
    elif state.graph_name:
        snap = db.scalar(
            select(Snapshot).where(
                Snapshot.repository_id == repo.id, Snapshot.graph_name == state.graph_name
            )
        )
    values = snap if revision else state
    return RepositoryView(
        id=repo.id,
        name=repo.name,
        source_type=repo.source_type,
        source=repo.source,
        branch=selected,
        status="ready" if revision else state.status,
        commit_sha=values.commit_sha,
        graph_name=values.graph_name,
        stats=values.stats,
        sync_state=values.sync_state,
        indexed_at=values.indexed_at,
        created_at=repo.created_at,
        snapshot_id=snap.id if snap else None,
        historical=bool(revision and snap.graph_name != state.graph_name),
        permission=db.get(Membership, (repo.id, user.id)).permission,
    )


def read_repository(
    repository_id: str,
    branch: str | None = Query(None, max_length=200),
    revision: str | None = Query(None, max_length=36),
    user: User = Depends(current_session),
    db: Session = Depends(db_session),
):
    return view_repository(db, user, repository_id, branch, revision)


def history_fingerprint(nodes, edges):
    if not nodes:
        return ""
    canonical = json.dumps(
        {
            "nodes": sorted(nodes, key=lambda n: n["id"]),
            "edges": sorted(
                [{k: v for k, v in e.items() if k != "id"} for e in edges],
                key=lambda e: (e["source"], e["target"], e["type"]),
            ),
        },
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def publish_snapshot(
    db, repo, branch, kind, graph_name, commit, stats, sync_state, indexed_at=None
):
    state = state_for_branch(db, repo, branch, create=True)
    state.graph_name, state.commit_sha, state.status = graph_name, commit, "ready"
    state.stats, state.sync_state = stats, sync_state
    state.indexed_at = indexed_at or utcnow()
    if branch == repo.branch:
        mirror = db.get(RepositoryBranch, (repo.id, branch))
        if mirror is None:
            mirror = RepositoryBranch(repository_id=repo.id, branch=branch)
            db.add(mirror)
        for key in ("graph_name", "commit_sha", "status", "stats", "sync_state", "indexed_at"):
            setattr(mirror, key, getattr(state, key))
    snapshot = db.scalar(select(Snapshot).where(Snapshot.graph_name == graph_name))
    if snapshot is None:
        snapshot = Snapshot(
            repository_id=repo.id,
            branch=branch,
            kind=kind,
            graph_name=graph_name,
            commit_sha=commit,
            stats=stats,
            sync_state=sync_state,
            indexed_at=state.indexed_at,
        )
        db.add(snapshot)
        db.flush()
    return snapshot
