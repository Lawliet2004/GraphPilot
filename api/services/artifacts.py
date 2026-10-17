"""Only redacted, bounded text is persisted. Expiry applies to every read."""

import hashlib
import os
import re
import uuid
from datetime import timedelta
from urllib.parse import unquote, urlparse

from fastapi import HTTPException
from sqlalchemy import select

from api.auth import audit
from api.config import settings
from api.db import SessionLocal, utcnow
from api.ingestion.python import stable_id
from api.models import LogArtifact
from api.services.runtime_config import log_policy

ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|$))")
ASSIGNMENT = re.compile(
    r"(?im)(\b(?:[\w-]*(?:password|passwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key)[\w-]*)\b[\"']?\s*[:=]\s*)[^\s,;]+"
)


class ArtifactLimitError(ValueError):
    pass


def redact(text):
    text = ANSI.sub("", text)
    text = "".join(c for c in text if c in "\n\t" or ord(c) >= 32 and ord(c) != 127)
    cfg = settings()
    database_password = urlparse(cfg.database_url).password or ""
    for secret in (
        cfg.github_token,
        cfg.llm_api_key,
        cfg.smtp_password,
        cfg.falkor_password,
        database_password,
        unquote(database_password),
    ):
        if secret:
            text = text.replace(secret, "[REDACTED]")
    text = re.sub(
        r"-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?-----END [^-]*PRIVATE KEY-----",
        "[REDACTED PRIVATE KEY]",
        text,
    )
    text = re.sub(
        r"(?i)(\b(?:authorization|proxy-authorization)\s*[:=]\s*)(?:bearer|basic)\s+[^\s]+",
        r"\1[REDACTED]",
        text,
    )
    text = re.sub(
        r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16}|sk-[A-Za-z0-9_-]{20,})\b",
        "[REDACTED]",
        text,
    )
    text = re.sub(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b", "[REDACTED JWT]", text)
    text = re.sub(r"(?i)([a-z][a-z0-9+.-]*://)[^\s/@]+:[^\s/@]+@", r"\1[REDACTED]@", text)
    return ASSIGNMENT.sub(r"\1[REDACTED]", text)


def artifact_path(row):
    root = settings().data_dir.resolve() / "logs"
    # No provider-controlled filenames, path fragments or signed URLs are stored.
    path = root / str(uuid.UUID(row.repository_id)) / (str(uuid.UUID(row.id)) + ".txt")
    if not path.resolve().is_relative_to(root) or path.is_symlink():
        raise HTTPException(404, "Log artifact is unavailable")
    return path


def persist_log(repo, source_id, text):
    redacted = redact(text)
    content = redacted.encode("utf-8")
    policy = log_policy()
    if len(content) > policy["max_log_bytes"]:
        raise ArtifactLimitError("Redacted log exceeds storage budget")
    digest = hashlib.sha256(content).hexdigest()
    identity = f"{repo.id}:{repo.branch}:{source_id}:{digest}"
    artifact_id = str(uuid.uuid5(uuid.NAMESPACE_URL, identity))
    node_id = stable_id(repo.id, repo.branch, "LogArtifact", artifact_id)
    with SessionLocal() as db:
        row = db.get(LogArtifact, artifact_id)
        if row is None:
            row = LogArtifact(
                id=artifact_id,
                repository_id=repo.id,
                branch=repo.branch,
                node_id=node_id,
                source_id=source_id,
                content_hash=digest,
                size_bytes=len(content),
                expires_at=utcnow() + timedelta(days=policy["artifact_retention_days"]),
            )
            path = artifact_path(row)
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            # Write once, atomically, with owner-only permissions. Never write raw text.
            temporary = path.with_suffix("." + uuid.uuid4().hex + ".tmp")
            try:
                fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as handle:
                    handle.write(content)
                os.replace(temporary, path)
                db.add(row)
                db.commit()
            finally:
                temporary.unlink(missing_ok=True)
        return {
            "id": row.id,
            "node_id": row.node_id,
            "size_bytes": row.size_bytes,
            "expires_at": row.expires_at.isoformat(),
            "content_hash": row.content_hash,
        }


def cached_log(repo, source_id):
    with SessionLocal() as db:
        row = db.scalar(
            select(LogArtifact)
            .where(
                LogArtifact.repository_id == repo.id,
                LogArtifact.branch == repo.branch,
                LogArtifact.source_id == source_id,
            )
            .order_by(LogArtifact.created_at.desc())
            .limit(1)
        )
        if row is None:
            return None
        return {
            "id": row.id,
            "node_id": row.node_id,
            "size_bytes": row.size_bytes,
            "expires_at": row.expires_at.isoformat(),
            "content_hash": row.content_hash,
        }


def pytest_failure_links(repo, saved, code_nodes, workflow_commit):
    """Link exact log-reported pytest node IDs only at the indexed source commit.

    This does not rerun tests or infer identity from a bare function name.
    Ambiguous declarations, other revisions and expired archives remain unlinked.
    """
    if not workflow_commit or workflow_commit != repo.commit_sha:
        return []
    with SessionLocal() as db:
        row = db.get(LogArtifact, saved["id"])
        if (
            not row
            or row.repository_id != repo.id
            or row.branch != repo.branch
            or row.purged_at
            or row.expires_at <= utcnow()
        ):
            return []
        path = artifact_path(row)
        if not path.is_file() or path.stat().st_size > 10_000_000:
            return []
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != row.content_hash:
            return []
    tests = {}
    for node in code_nodes:
        if node["type"] == "TestCase":
            key = (node["path"], node["qualified_name"])
            tests.setdefault(key, []).append(node["id"])
    links = {}
    pattern = r"(?:^|\s)FAILED\s+([A-Za-z0-9_./-]+\.py(?:::[A-Za-z0-9_]+){1,5})(?:\[[^\r\n\]]{0,500}\])?(?=\s|$)"
    for match in re.finditer(pattern, content.decode("utf-8"), re.MULTILINE):
        parts = match[1].split("::")
        key = (parts[0].removeprefix("./"), ".".join(parts[1:]))
        targets = tests.get(key, [])
        if len(targets) == 1:
            links[targets[0]] = {
                "source": saved["node_id"],
                "target": targets[0],
                "type": "RELATED_TO",
                "provenance": "pytest-failure-nodeid",
                "verification": "Log-reported failure at the indexed commit; test not rerun",
            }
        if len(links) >= 100:
            break
    return list(links.values())


def read_log(db, repo, artifact_id, known_node=None):
    row = db.get(LogArtifact, artifact_id)
    if not row or row.repository_id != repo.id or row.branch != repo.branch:
        raise HTTPException(404, "Log artifact not found in this branch")
    from api.graph import store

    found = (
        known_node
        if known_node is not None
        else store.find_node(repo.graph_name, row.node_id)
        if repo.graph_name
        else None
    )
    if not found or found.get("id") != row.node_id or found.get("artifact_id") != row.id:
        raise HTTPException(404, "Log artifact is absent from this snapshot")
    if row.expires_at <= utcnow() or row.purged_at:
        raise HTTPException(410, "Log retention has expired; archived content is unavailable")
    path = artifact_path(row)
    if not path.is_file() or path.stat().st_size > 10_000_000:
        raise HTTPException(404, "Log artifact is unavailable")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != row.content_hash:
        raise HTTPException(409, "Log artifact integrity check failed")
    return row, content.decode("utf-8")


def purge_expired_logs():
    count, size = 0, 0
    with SessionLocal() as db:
        rows = db.scalars(
            select(LogArtifact)
            .where(LogArtifact.expires_at <= utcnow(), LogArtifact.purged_at.is_(None))
            .limit(100)
            .with_for_update(skip_locked=True)
        )
        for row in rows:
            artifact_path(row).unlink(missing_ok=True)
            row.purged_at = utcnow()
            count += 1
            size += row.size_bytes
        if count:
            audit(db, None, "system.expired_logs_purged", count=count, bytes=size)
        db.commit()
    return {"artifacts": count, "bytes": size}
