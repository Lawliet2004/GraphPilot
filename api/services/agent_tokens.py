"""Read-only agent credentials never inherit administrative bypasses."""

import secrets
from datetime import timedelta

from fastapi import HTTPException

from api.auth import audit, digest
from api.db import utcnow
from api.models import AgentToken, User


def issue_token(db, user, name, days=7, scopes=None):
    scopes = ["read"] if scopes is None else scopes
    if (
        not isinstance(scopes, list)
        or "read" not in scopes
        or set(scopes) - {"read", "repositories:write"}
    ):
        raise ValueError("Only read and repository management scopes are supported")
    if user.disabled or not 1 <= days <= 30 or not name.strip() or len(name) > 80:
        raise ValueError("Use an active account, a name of 1–80 characters and 1–30 days")
    raw = "gp_mcp_" + secrets.token_urlsafe(32)
    row = AgentToken(
        id=digest(raw),
        user_id=user.id,
        name=name.strip(),
        expires_at=utcnow() + timedelta(days=days),
        scopes=sorted(set(scopes)),
    )
    db.add(row)
    audit(db, user.id, "mcp.token_created", row.id, name=row.name, days=days)
    db.flush()
    return raw, row


def authenticate_token(db, raw):
    if not raw.startswith("gp_mcp_") or len(raw) > 128:
        raise HTTPException(401, "Invalid or expired MCP token")
    row = db.get(AgentToken, digest(raw))
    user = db.get(User, row.user_id) if row else None
    if not row or row.revoked_at or row.expires_at <= utcnow() or not user or user.disabled:
        raise HTTPException(401, "Invalid or expired MCP token")
    return user


def revoke_token(db, token_id):
    row = db.get(AgentToken, token_id)
    if row is None:
        raise ValueError("MCP token not found")
    row.revoked_at = utcnow()
    audit(db, row.user_id, "mcp.token_revoked", row.id)
