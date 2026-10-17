"""Browser approval pairs a CLI with scoped credentials; no password or shell API."""

import hmac
import re
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from api.auth import audit, auth_rate_limit, current_session, digest
from api.config import settings
from api.db import db_session, utcnow
from api.models import AgentToken, AuthorizationRequest
from api.services.agent_tokens import issue_token
from api.services.github_connection import challenge

router = APIRouter(prefix="/api/cli", tags=["CLI access"])


class DeviceStart(BaseModel):
    challenge: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")
    name: str = Field(default="GraphPilot CLI", min_length=1, max_length=80)
    write: bool = False


@router.post("/device", status_code=201)
def start(body: DeviceStart, request: Request, db=Depends(db_session)):
    auth_rate_limit(db, request)
    db.execute(delete(AuthorizationRequest).where(AuthorizationRequest.expires_at < utcnow()))
    raw = secrets.token_urlsafe(32)
    code = secrets.token_hex(4).upper()
    scopes = ["read", "repositories:write"] if body.write else ["read"]
    db.add(
        AuthorizationRequest(
            id=digest(raw),
            kind="cli",
            code=code,
            verifier=body.challenge,
            name=body.name,
            scopes=scopes,
            expires_at=utcnow() + timedelta(minutes=10),
        )
    )
    db.commit()
    return {
        "device_code": raw,
        "user_code": code[:4] + "-" + code[4:],
        "verification_uri": settings().public_url + "/cli/authorize?code=" + code,
        "expires_in": 600,
        "interval": 5,
    }


def find_code(db, code):
    code = code.replace("-", "").upper()
    if not re.fullmatch(r"[A-F0-9]{8}", code):
        raise HTTPException(404, "CLI request was not found or has expired")
    row = db.scalar(
        select(AuthorizationRequest)
        .where(AuthorizationRequest.code == code, AuthorizationRequest.kind == "cli")
        .with_for_update()
    )
    if not row or row.expires_at <= utcnow() or row.status != "pending":
        raise HTTPException(404, "CLI request was not found or has expired")
    return row


@router.get("/device/{code}")
def inspect(code: str, request: Request, user=Depends(current_session), db=Depends(db_session)):
    auth_rate_limit(db, request)
    row = find_code(db, code)
    return {"name": row.name, "scopes": row.scopes, "expires_at": row.expires_at}


class Approval(BaseModel):
    approve: bool


@router.post("/device/{code}/approve")
def approve(
    code: str,
    body: Approval,
    request: Request,
    user=Depends(current_session),
    db=Depends(db_session),
):
    auth_rate_limit(db, request)
    row = find_code(db, code)
    row.status = "approved" if body.approve else "denied"
    row.user_id = user.id
    audit(db, user.id, "cli.approved" if body.approve else "cli.denied", row.id, scopes=row.scopes)
    db.commit()
    return {
        "message": "CLI approved. Return to your terminal."
        if body.approve
        else "CLI request denied."
    }


class Poll(BaseModel):
    device_code: str = Field(min_length=20, max_length=100)
    verifier: str = Field(pattern=r"^[A-Za-z0-9_-]{43,128}$")


@router.post("/device/poll")
def poll(body: Poll, response: Response, db=Depends(db_session)):
    row = db.scalar(
        select(AuthorizationRequest)
        .where(AuthorizationRequest.id == digest(body.device_code))
        .with_for_update()
    )
    if not row or row.kind != "cli" or row.expires_at <= utcnow() or row.status == "consumed":
        raise HTTPException(410, "CLI request expired. Start login again.")
    if not hmac.compare_digest(row.verifier, challenge(body.verifier)):
        raise HTTPException(403, "CLI verifier did not match")
    if row.last_poll_at and row.last_poll_at > utcnow() - timedelta(seconds=5):
        raise HTTPException(429, "Wait five seconds before polling again")
    row.last_poll_at = utcnow()
    if row.status == "pending":
        db.commit()
        response.status_code = 202
        return {"status": "pending"}
    if row.status == "denied":
        db.commit()
        raise HTTPException(403, "CLI access was denied")
    from api.models import User

    user = db.get(User, row.user_id)
    if not user or user.disabled:
        raise HTTPException(403, "This account cannot authorize a CLI")
    token, credential = issue_token(db, user, row.name, 7, scopes=row.scopes)
    row.status = "consumed"
    db.commit()
    return {
        "status": "approved",
        "token": token,
        "id": credential.id,
        "expires_at": credential.expires_at,
        "scopes": credential.scopes,
    }


@router.get("/tokens")
def tokens(user=Depends(current_session), db=Depends(db_session)):
    rows = db.scalars(
        select(AgentToken)
        .where(AgentToken.user_id == user.id)
        .order_by(AgentToken.created_at.desc())
        .limit(100)
    )
    return [
        {
            "id": r.id,
            "name": r.name,
            "scopes": r.scopes,
            "expires_at": r.expires_at,
            "revoked": bool(r.revoked_at),
        }
        for r in rows
    ]


@router.delete("/tokens/{token_id}")
def revoke(token_id: str, user=Depends(current_session), db=Depends(db_session)):
    row = db.get(AgentToken, token_id)
    if not row or row.user_id != user.id:
        raise HTTPException(404, "Credential not found")
    row.revoked_at = utcnow()
    audit(db, user.id, "mcp.token_revoked", row.id)
    db.commit()
    return {"message": "Credential revoked"}


@router.post("/logout")
def logout(request: Request, user=Depends(current_session), db=Depends(db_session)):
    row = getattr(request.state, "agent_token", None)
    if not row:
        raise HTTPException(400, "Use the CLI credential to sign out")
    row.revoked_at = utcnow()
    audit(db, user.id, "cli.logout", row.id)
    db.commit()
    return {"message": "CLI signed out"}
