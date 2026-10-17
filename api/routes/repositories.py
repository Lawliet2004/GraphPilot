import shutil
import uuid
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, union_all
from sqlalchemy.orm import Session

from api.auth import audit, current_session
from api.config import settings
from api.db import SessionLocal, db_session
from api.graph import store
from api.ingestion.sources import SourceError, github_url, local_path, validate_branch
from api.models import (
    Audit,
    Conversation,
    Job,
    Membership,
    Repository,
    RepositoryBranch,
    Snapshot,
    User,
)
from api.services.permissions import indexed, repository_access
from api.services.revisions import RepositoryView, read_repository, state_for_branch

router = APIRouter(prefix="/api", tags=["repositories"])


def repository_json(repo):
    # Never disclose server-local filesystem locations or archive storage paths.
    return {
        k: getattr(repo, k)
        for k in (
            "id",
            "name",
            "source_type",
            "branch",
            "status",
            "commit_sha",
            "stats",
            "sync_state",
            "indexed_at",
            "created_at",
        )
    } | {
        "source_url": repo.source if repo.source_type == "github" else None,
        "snapshot_id": getattr(repo, "snapshot_id", None),
        "historical": getattr(repo, "historical", False),
        "permission": getattr(repo, "permission", None),
    }


def job_json(job):
    return {
        k: getattr(job, k)
        for k in (
            "id",
            "repository_id",
            "branch",
            "kind",
            "status",
            "progress",
            "message",
            "attempts",
            "cancel_requested",
            "result",
            "created_at",
            "finished_at",
        )
    }


class ConnectRepository(BaseModel):
    source_type: Literal["github", "local"]
    source: str = Field(min_length=1, max_length=2000)
    branch: str = Field(default="main", pattern=r"^[A-Za-z0-9_][A-Za-z0-9_./-]{0,199}$")


def add_repository(db, user, source_type, source, branch, name):
    repo = Repository(
        name=name[:100], owner_id=user.id, source_type=source_type, source=source, branch=branch
    )
    db.add(repo)
    db.flush()
    db.add(Membership(repository_id=repo.id, user_id=user.id, permission="owner"))
    job = Job(repository_id=repo.id, requested_by=user.id, branch=branch)
    db.add(job)
    audit(db, user.id, "repository.connect", repo.id, source_type=source_type)
    db.commit()
    return {"repository": repository_json(repo), "job": job_json(job)}


@router.post("/repositories", status_code=201)
def connect(
    body: ConnectRepository,
    user: User = Depends(current_session),
    db: Session = Depends(db_session),
):
    try:
        validate_branch(body.branch)
        if body.source_type == "github":
            source = github_url(body.source)
            name = source.rsplit("/", 1)[-1]
        else:
            path = local_path(body.source)
            source, name = str(path), path.name
    except (SourceError, OSError, ValueError) as exc:
        message = str(exc) if isinstance(exc, SourceError) else "Source directory is unavailable"
        raise HTTPException(422, message) from None
    return add_repository(db, user, body.source_type, source, body.branch, name)


@router.post("/repositories/upload", status_code=201)
def upload(
    file: UploadFile = File(),
    branch: str = Form("upload"),
    user: User = Depends(current_session),
    db: Session = Depends(db_session),
):
    cfg = settings()
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(422, "Choose a source ZIP archive")
    if len(branch) > 200 or not branch.strip():
        raise HTTPException(422, "Enter a branch label of up to 200 characters")
    path = cfg.data_dir.resolve() / "uploads" / f"{uuid.uuid4()}.zip"
    path.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    try:
        with path.open("wb") as output:
            while chunk := file.file.read(65536):
                size += len(chunk)
                if size > cfg.max_archive_bytes:
                    raise HTTPException(413, "Archive exceeds the 25 MB upload limit")
                output.write(chunk)
        # Fully validate before committing a durable job.
        from api.ingestion.sources import extract_zip

        check = path.with_suffix("")
        try:
            extract_zip(path, check)
        finally:
            shutil.rmtree(check, ignore_errors=True)
        return add_repository(db, user, "archive", str(path), branch, Path(file.filename).stem)
    except SourceError as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(422, str(exc)) from None
    except Exception:
        path.unlink(missing_ok=True)
        raise


@router.get("/repositories")
def repositories(user: User = Depends(current_session), db: Session = Depends(db_session)):
    rows = db.scalars(
        select(Repository)
        .join(Membership)
        .where(Membership.user_id == user.id, Repository.status != "deleting")
        .order_by(Repository.created_at.desc())
    )
    return [repository_json(repo) for repo in rows]


@router.get("/repositories/{repository_id}")
def repository(
    repository_id: str,
    user: User = Depends(current_session),
    db: Session = Depends(db_session),
    repo: RepositoryView = Depends(read_repository),
):
    return repository_json(repo)


@router.post("/repositories/{repository_id}/jobs", status_code=201)
def enqueue(
    repository_id: str,
    kind: Literal["index", "github-sync"] = "index",
    branch: str | None = Query(None, max_length=200),
    revision: str | None = Query(None, max_length=36),
    user: User = Depends(current_session),
    db: Session = Depends(db_session),
):
    repo = repository_access(db, user, repository_id, write=True)
    if revision:
        raise HTTPException(
            422, "Historical snapshots are read-only. Select the latest branch before syncing."
        )
    selected_branch = branch or repo.branch
    state_for_branch(db, repo, selected_branch)
    # Lock serializes concurrent requests to avoid duplicate active jobs.
    db.refresh(repo, with_for_update=True)
    if repo.status == "deleting":
        raise HTTPException(409, "Repository removal is in progress")
    if kind == "github-sync" and repo.source_type != "github":
        raise HTTPException(422, "GitHub sync is only available for GitHub repositories")
    if db.scalar(
        select(Job).where(Job.repository_id == repository_id, Job.status.in_(["queued", "running"]))
    ):
        raise HTTPException(409, "This repository already has an active job")
    job = Job(repository_id=repository_id, requested_by=user.id, kind=kind, branch=selected_branch)
    db.add(job)
    audit(db, user.id, "job.enqueue", repository_id, kind=kind, branch=selected_branch)
    db.commit()
    return job_json(job)


class RemoveRepository(BaseModel):
    confirm_name: str = Field(min_length=1, max_length=100)


@router.delete("/repositories/{repository_id}", status_code=202)
def remove_repository(
    repository_id: str,
    body: RemoveRepository,
    user: User = Depends(current_session),
    db: Session = Depends(db_session),
):
    repo = repository_access(db, user, repository_id, allow_deleting=True)
    if repo.owner_id != user.id:
        raise HTTPException(403, "Repository ownership required")
    db.refresh(repo, with_for_update=True)
    if body.confirm_name != repo.name:
        raise HTTPException(422, "Enter the repository name exactly to confirm removal")
    if db.scalar(
        select(Job.id).where(Job.repository_id == repo.id, Job.status.in_(["queued", "running"]))
    ):
        raise HTTPException(
            409, "Wait for active jobs to finish or cancel them before removing this repository"
        )
    repo.status = "deleting"
    job = Job(repository_id=repo.id, requested_by=user.id, branch=repo.branch, kind="delete")
    db.add(job)
    audit(db, user.id, "repository.removal_requested", repo.id)
    db.commit()
    return job_json(job)


@router.get("/repositories/{repository_id}/jobs")
def jobs(
    repository_id: str,
    branch: str | None = Query(None, max_length=200),
    user: User = Depends(current_session),
    db: Session = Depends(db_session),
):
    repository_access(db, user, repository_id)
    return [
        job_json(job)
        for job in db.scalars(
            select(Job)
            .where(Job.repository_id == repository_id, Job.branch == branch if branch else True)
            .order_by(Job.created_at.desc())
            .limit(30)
        )
    ]


@router.post("/jobs/{job_id}/cancel")
def cancel(job_id: str, user: User = Depends(current_session), db: Session = Depends(db_session)):
    job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
    if not job:
        raise HTTPException(404, "Job not found")
    repository_access(db, user, job.repository_id, write=True)
    if job.status not in {"queued", "running"}:
        raise HTTPException(409, "Only active jobs can be cancelled")
    job.cancel_requested = True
    if job.status == "queued":
        job.status, job.message = "cancelled", "Cancelled before execution"
    audit(db, user.id, "job.cancel", job.id)
    db.commit()
    return job_json(job)


@router.get("/repositories/{repository_id}/graph")
def graph(
    repository_id: str,
    limit: int = Query(80, ge=1, le=200),
    kind: str = "",
    relation: str = "",
    q: str = Query("", max_length=200),
    user: User = Depends(current_session),
    db: Session = Depends(db_session),
    repo: RepositoryView = Depends(read_repository),
):
    if kind and kind not in store.NODE_TYPES:
        raise HTTPException(422, "Unknown node type")
    if relation and relation not in store.EDGE_TYPES:
        raise HTTPException(422, "Unknown relationship type")
    return store.subgraph(indexed(repo), limit, kind, q, relation) | {
        "commit": repo.commit_sha,
        "snapshot_id": repo.snapshot_id,
        "historical": repo.historical,
        "branch": repo.branch,
    }


@router.get("/repositories/{repository_id}/nodes/{node_id}")
def node(
    repository_id: str,
    node_id: str,
    user: User = Depends(current_session),
    db: Session = Depends(db_session),
    repo: RepositoryView = Depends(read_repository),
):
    result = store.find_node(indexed(repo), node_id)
    if not result:
        raise HTTPException(404, "Node not found in this repository snapshot")
    return result


@router.get("/repositories/{repository_id}/nodes/{node_id}/neighbors")
def neighbors(
    repository_id: str,
    node_id: str,
    relation: str = "",
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(current_session),
    db: Session = Depends(db_session),
    repo: RepositoryView = Depends(read_repository),
):
    if relation and relation not in store.EDGE_TYPES:
        raise HTTPException(422, "Unknown relationship type")
    if not store.find_node(indexed(repo), node_id):
        raise HTTPException(404, "Node not found")
    return store.neighbors(repo.graph_name, node_id, limit, relation)


@router.get("/repositories/{repository_id}/search")
def search(
    repository_id: str,
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(20, ge=1, le=50),
    user: User = Depends(current_session),
    db: Session = Depends(db_session),
    repo: RepositoryView = Depends(read_repository),
):
    return {
        "results": store.search(indexed(repo), q, limit),
        "branch": repo.branch,
        "commit": repo.commit_sha,
        "snapshot_id": repo.snapshot_id,
        "historical": repo.historical,
    }


@router.get("/repositories/{repository_id}/impact/{node_id}")
def impact(
    repository_id: str,
    node_id: str,
    depth: int = Query(2, ge=1, le=3),
    user: User = Depends(current_session),
    db: Session = Depends(db_session),
    repo: RepositoryView = Depends(read_repository),
):
    if not store.find_node(indexed(repo), node_id):
        raise HTTPException(404, "Node not found")
    return store.impact(repo.graph_name, node_id, depth)


@router.get("/repositories/{repository_id}/paths")
def paths(
    repository_id: str,
    source: str,
    target: str,
    depth: int = Query(3, ge=1, le=4),
    user: User = Depends(current_session),
    db: Session = Depends(db_session),
    repo: RepositoryView = Depends(read_repository),
):
    graph_name = indexed(repo)
    if not store.find_node(graph_name, source) or not store.find_node(graph_name, target):
        raise HTTPException(404, "One or both nodes are absent from this snapshot")
    return {"paths": store.find_path(graph_name, source, target, depth), "max_depth": depth}


@router.get("/repositories/{repository_id}/evidence/{node_id}")
def evidence(
    repository_id: str,
    node_id: str,
    user: User = Depends(current_session),
    db: Session = Depends(db_session),
    repo: RepositoryView = Depends(read_repository),
):
    return read_evidence(repo, node_id)


def read_evidence(repo, node_id):
    found = store.find_node(indexed(repo), node_id)
    if not found:
        raise HTTPException(404, "Node not found")
    if found.get("type") == "LogArtifact" and found.get("artifact_id"):
        from api.services.artifacts import read_log

        with SessionLocal() as db:
            try:
                _, content = read_log(db, repo, found["artifact_id"], known_node=found)
                excerpt = content[:12000]
                notice = "Automated redaction is best effort. Unknown secret formats may remain."
            except HTTPException as exc:
                if exc.status_code not in {404, 410}:
                    raise
                excerpt, notice = "", str(exc.detail)
        return {
            "node": found,
            "content": excerpt,
            "start_line": 1 if excerpt else None,
            "end_line": len(excerpt.splitlines()) if excerpt else None,
            "commit": found.get("commit") or repo.commit_sha,
            "snapshot_id": repo.snapshot_id,
            "historical": repo.historical,
            "url": found.get("url"),
            "truncated": len(excerpt) == 12000,
            "notice": notice,
            "download_url": f"/api/repositories/{repo.id}/artifacts/{found['artifact_id']}",
        }
    if not found.get("path"):
        return {
            "node": found,
            "content": found.get("body") or found.get("summary") or "",
            "url": found.get("url"),
            "start_line": None,
            "end_line": None,
            "commit": found.get("sha")
            if found["type"] in {"Commit", "WorkflowRun"}
            else repo.commit_sha,
            "snapshot_id": repo.snapshot_id,
            "historical": repo.historical,
        }
    root = settings().data_dir.resolve() / "snapshots" / repo.id / repo.stats["tree_hash"]
    path = (root / found["path"]).resolve()
    if not path.is_relative_to(root) or not path.is_file() or path.is_symlink():
        raise HTTPException(404, "Source artifact is unavailable")
    content = path.read_text().splitlines()
    start = max(1, found.get("line", 1) - 3)
    end = min(len(content), found.get("end_line", start) + 3, start + 199)
    url = (
        f"{repo.source}/blob/{repo.commit_sha}/{quote(found['path'], safe='/')}#L{start}"
        if repo.source_type == "github"
        else None
    )
    return {
        "node": found,
        "content": "\n".join(content[start - 1 : end]),
        "start_line": start,
        "end_line": end,
        "truncated": end < found.get("end_line", 0),
        "commit": repo.commit_sha,
        "snapshot_id": repo.snapshot_id,
        "historical": repo.historical,
        "url": url,
    }


@router.get("/repositories/{repository_id}/artifacts/{artifact_id}")
def download_artifact(
    repository_id: str,
    artifact_id: str,
    repo: RepositoryView = Depends(read_repository),
    user: User = Depends(current_session),
    db: Session = Depends(db_session),
):
    from api.services.artifacts import read_log

    row, content = read_log(db, repo, artifact_id)
    audit(db, user.id, "artifact.download", row.id, repository_id=repo.id, branch=repo.branch)
    db.commit()
    return PlainTextResponse(
        content,
        headers={
            "Content-Disposition": f'attachment; filename="ci-log-{row.id}.txt"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


@router.get("/activity")
def activity(user: User = Depends(current_session), db: Session = Depends(db_session)):
    rows = db.scalars(
        select(Audit).where(Audit.user_id == user.id).order_by(Audit.created_at.desc()).limit(20)
    )
    return [
        {"id": a.id, "action": a.action, "target": a.target, "created_at": a.created_at}
        for a in rows
    ]


@router.get("/workspace/recent")
def recent_workspace(user: User = Depends(current_session), db: Session = Depends(db_session)):
    queries = [
        {
            "id": c.id,
            "question": c.question,
            "repository_id": c.repository_id,
            "repository_name": name,
            "branch": c.branch,
            "snapshot_id": c.snapshot_id,
            "created_at": c.created_at,
        }
        for c, name in db.execute(
            select(Conversation, Repository.name)
            .join(Repository, Repository.id == Conversation.repository_id)
            .join(Membership, Membership.repository_id == Repository.id)
            .where(Conversation.user_id == user.id, Membership.user_id == user.id)
            .order_by(Conversation.created_at.desc())
            .limit(5)
        )
    ]
    heads = union_all(
        select(Repository.id.label("repo_id"), Repository.graph_name.label("graph")),
        select(RepositoryBranch.repository_id, RepositoryBranch.graph_name)
        .join(Repository, Repository.id == RepositoryBranch.repository_id)
        .where(RepositoryBranch.branch != Repository.branch),
    ).subquery()
    snapshots = db.execute(
        select(Snapshot, Repository.name)
        .join(
            heads,
            (heads.c.repo_id == Snapshot.repository_id) & (heads.c.graph == Snapshot.graph_name),
        )
        .join(Repository, Repository.id == Snapshot.repository_id)
        .join(Membership, Membership.repository_id == Repository.id)
        .where(Membership.user_id == user.id)
        .order_by(Snapshot.created_at.desc())
        .limit(10)
    ).all()
    failures, warnings = [], []
    for snapshot, name in snapshots:
        from api.services.lifecycle import storage_read_lock

        storage_read_lock(db, snapshot.repository_id)
        if db.scalar(select(Repository.status).where(Repository.id == snapshot.repository_id)) in {
            None,
            "deleting",
        }:
            continue
        try:
            rows = store.query(
                snapshot.graph_name,
                "MATCH (n:WorkflowRun) WHERE n.status = 'failure' RETURN n ORDER BY n.timestamp DESC LIMIT 3",
            )
        except Exception:
            warnings.append("Some CI history could not be read. Open the repository to retry.")
            continue
        for row in rows:
            failures.append(
                {
                    "node": store.encode_node(row[0]),
                    "repository_id": snapshot.repository_id,
                    "repository_name": name,
                    "branch": snapshot.branch,
                    "snapshot_id": snapshot.id,
                }
            )
    failures.sort(key=lambda item: item["node"].get("timestamp", ""), reverse=True)
    return {
        "queries": queries,
        "failures": failures[:5],
        "warnings": sorted(set(warnings)),
        "coverage": "CI history from up to 10 latest authorized branch heads; unavailable history is not inferred.",
    }


@router.get("/repositories/{repository_id}/history")
def history(
    repository_id: str,
    kind: str = "",
    user: User = Depends(current_session),
    db: Session = Depends(db_session),
    repo: RepositoryView = Depends(read_repository),
):
    allowed = {"Commit", "Issue", "PullRequest", "WorkflowRun", "LogArtifact", "Decision"}
    if kind and kind not in allowed:
        raise HTTPException(422, "Unknown history entity type")
    rows = (
        store.query(
            indexed(repo),
            "MATCH (n:Entity) WHERE n.type IN $types RETURN n ORDER BY n.timestamp DESC LIMIT 200",
            {"types": [kind] if kind else sorted(allowed)},
        )
        if repo.graph_name
        else []
    )
    items = [store.encode_node(row[0]) for row in rows]
    return {
        "items": items,
        "sync": repo.sync_state,
        "coverage": "GitHub metadata synchronized so far. PR detail pages resume across jobs; GitHub exposes at most 250 PR commits and 3000 PR changed files. Missing links and unavailable logs are not inferred.",
    }


class BranchInput(BaseModel):
    branch: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_][A-Za-z0-9_./-]*$")


@router.get("/repositories/{repository_id}/branches")
def branches(
    repository_id: str, user: User = Depends(current_session), db: Session = Depends(db_session)
):
    from api.models import RepositoryBranch

    repo = repository_access(db, user, repository_id)
    rows = list(
        db.scalars(select(RepositoryBranch).where(RepositoryBranch.repository_id == repo.id))
    )
    other = [
        {k: getattr(r, k) for k in ("branch", "status", "commit_sha", "indexed_at")}
        for r in rows
        if r.branch != repo.branch
    ]
    return {
        "default_branch": repo.branch,
        "branches": [
            {k: getattr(repo, k) for k in ("branch", "status", "commit_sha", "indexed_at")},
            *sorted(other, key=lambda r: r["branch"]),
        ],
    }


@router.post("/repositories/{repository_id}/branches", status_code=201)
def connect_branch(
    repository_id: str,
    body: BranchInput,
    user: User = Depends(current_session),
    db: Session = Depends(db_session),
):
    from api.models import RepositoryBranch

    repo = repository_access(db, user, repository_id, write=True)
    db.refresh(repo, with_for_update=True)
    if repo.status == "deleting":
        raise HTTPException(409, "Repository removal is in progress")
    if repo.source_type == "archive":
        raise HTTPException(
            422,
            "A source archive is a fixed snapshot. Upload a separate archive for another branch.",
        )
    try:
        validate_branch(body.branch)
    except SourceError as exc:
        raise HTTPException(422, str(exc)) from None
    if body.branch == repo.branch or db.get(RepositoryBranch, (repo.id, body.branch)):
        raise HTTPException(409, "This branch is already connected")
    if db.scalar(
        select(Job).where(Job.repository_id == repo.id, Job.status.in_(["queued", "running"]))
    ):
        raise HTTPException(
            409, "Wait for the active repository job before connecting another branch"
        )
    state_for_branch(db, repo, body.branch, create=True)
    job = Job(repository_id=repo.id, requested_by=user.id, kind="index", branch=body.branch)
    db.add(job)
    audit(db, user.id, "repository.branch_connected", repo.id, branch=body.branch)
    db.commit()
    return {"branch": body.branch, "job": job_json(job)}


@router.get("/repositories/{repository_id}/snapshots")
def snapshots(
    repository_id: str,
    limit: int = Query(50, ge=1, le=100),
    repo: RepositoryView = Depends(read_repository),
    db: Session = Depends(db_session),
):
    from api.models import Snapshot

    rows = db.scalars(
        select(Snapshot)
        .where(
            Snapshot.repository_id == repo.id,
            Snapshot.branch == repo.branch,
            Snapshot.retired_at.is_(None),
        )
        .order_by(Snapshot.created_at.desc())
        .limit(limit)
    )
    return [
        {
            "id": s.id,
            "branch": s.branch,
            "commit_sha": s.commit_sha,
            "kind": s.kind,
            "created_at": s.created_at,
            "current": s.graph_name
            == state_for_branch(db, db.get(Repository, repo.id), repo.branch).graph_name,
        }
        for s in rows
    ]
