import hmac
import secrets
from datetime import timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from api.auth import audit, current_session, digest
from api.config import settings
from api.db import db_session, utcnow
from api.models import AuthorizationRequest, GitHubConnection
from api.routes.repositories import add_repository
from api.services import github_connection as gh

router = APIRouter(prefix="/api/integrations/github", tags=["GitHub connection"])


@router.get("")
def status(user=Depends(current_session), db=Depends(db_session)):
    row = db.get(GitHubConnection, user.id)
    return {
        "configured": gh.enabled(),
        "connected": bool(row),
        "login": row.login if row else None,
        "install_url": f"https://github.com/apps/{settings().github_app_slug}/installations/new"
        if gh.enabled()
        else None,
    }


@router.post("/authorize")
def authorize(request: Request, user=Depends(current_session), db=Depends(db_session)):
    if not gh.enabled():
        raise HTTPException(503, "The administrator needs to configure the GitHub App")
    if not getattr(request.state, "session", None):
        raise HTTPException(403, "Authorize GitHub from a browser session")
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    db.execute(
        delete(AuthorizationRequest).where(
            AuthorizationRequest.kind == "github", AuthorizationRequest.user_id == user.id
        )
    )
    db.add(
        AuthorizationRequest(
            id=digest(state),
            kind="github",
            user_id=user.id,
            session_id=request.state.session.id,
            verifier=gh.seal(verifier),
            expires_at=utcnow() + timedelta(minutes=10),
        )
    )
    db.commit()
    url = "https://github.com/login/oauth/authorize?" + urlencode(
        {
            "client_id": settings().github_client_id,
            "redirect_uri": settings().public_url + "/api/integrations/github/callback",
            "state": state,
            "code_challenge": gh.challenge(verifier),
            "code_challenge_method": "S256",
            "scope": "offline_access",
            "prompt": "select_account",
        }
    )
    from fastapi.responses import JSONResponse

    response = JSONResponse({"url": url})
    response.set_cookie(
        "gp_github_state",
        state,
        max_age=600,
        httponly=True,
        secure=settings().cookie_secure,
        samesite="lax",
        path="/api/integrations/github",
    )
    return response


@router.get("/callback")
def callback(
    request: Request,
    state: str = Query(max_length=200),
    code: str = Query(default="", max_length=500),
    error: str = "",
    user=Depends(current_session),
    db=Depends(db_session),
):
    cookie = request.cookies.get("gp_github_state", "")
    row = db.scalar(
        select(AuthorizationRequest)
        .where(AuthorizationRequest.id == digest(state))
        .with_for_update()
    )
    if (
        not cookie
        or not hmac.compare_digest(cookie, state)
        or not row
        or row.kind != "github"
        or row.user_id != user.id
        or row.session_id != request.state.session.id
        or row.expires_at <= utcnow()
    ):
        raise HTTPException(400, "GitHub authorization expired or did not match this browser")
    verifier = gh.unseal(row.verifier)
    db.delete(row)
    db.commit()  # A state can be consumed once, including upstream failure.
    result_path = "/connect?github=denied"
    if not error and code:
        result = gh.oauth(
            {
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": settings().public_url + "/api/integrations/github/callback",
            }
        )
        identity = gh.request("GET", "/user", token=result["access_token"])
        if not identity.get("id") or not identity.get("login"):
            raise HTTPException(403, "GitHub did not confirm an account identity")
        connection = db.get(GitHubConnection, user.id)
        if connection and connection.github_user_id != str(identity["id"]):
            raise HTTPException(
                409, "Disconnect the existing GitHub account before connecting another"
            )
        if not connection:
            connection = GitHubConnection(
                user_id=user.id, github_user_id=str(identity["id"]), login=identity["login"]
            )
            db.add(connection)
        gh.update_tokens(connection, result)
        audit(db, user.id, "github.connected", user.id)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                409, "This GitHub account is already linked to another GraphPilot account"
            ) from None
        result_path = "/connect?github=connected"
    response = RedirectResponse(settings().public_url + result_path, status_code=303)
    response.delete_cookie("gp_github_state", path="/api/integrations/github")
    return response


@router.delete("")
def disconnect(user=Depends(current_session), db=Depends(db_session)):
    db.execute(delete(GitHubConnection).where(GitHubConnection.user_id == user.id))
    audit(db, user.id, "github.disconnected", user.id)
    db.commit()
    return {
        "message": "Disconnected. Existing indexed snapshots remain until you remove their repositories."
    }


@router.get("/installations")
def installations(user=Depends(current_session)):
    items = gh.installations(gh.token_for(user.id))
    return [
        {"id": i["id"], "account": i.get("account", {}).get("login", "GitHub account")}
        for i in items
    ]


@router.get("/installations/{installation_id}/repositories")
def repositories(
    installation_id: int, page: int = Query(default=1, ge=1, le=100), user=Depends(current_session)
):
    rows, total = gh.repositories(gh.token_for(user.id), installation_id, page)
    return {
        "repositories": [
            {
                "id": r["id"],
                "full_name": r["full_name"],
                "private": r["private"],
                "default_branch": r["default_branch"],
                "installation_id": installation_id,
            }
            for r in rows
        ],
        "total_count": total,
        "page": page,
        "has_more": page * 100 < total,
    }


class Connect(BaseModel):
    installation_id: int = Field(gt=0)
    repository_id: int = Field(gt=0)
    branch: str | None = Field(default=None, max_length=200)


@router.post("/repositories", status_code=201)
def connect(body: Connect, user=Depends(current_session), db=Depends(db_session)):
    from api.ingestion.sources import SourceError, github_url, validate_branch

    token = gh.token_for(user.id)
    # GitHub user tokens enforce the intersection of user and selected App access.
    if body.installation_id not in {int(i["id"]) for i in gh.installations(token)}:
        raise HTTPException(404, "GitHub installation not found")
    selected = None
    for page in range(1, 11):
        rows, total = gh.repositories(token, body.installation_id, page)
        selected = next((r for r in rows if r["id"] == body.repository_id), None)
        if selected or page * 100 >= total:
            break
    if not selected:
        raise HTTPException(404, "Repository was not found in your selected GitHub installation")
    try:
        source = github_url(selected["html_url"])
        branch = body.branch or selected["default_branch"]
        validate_branch(branch)
    except SourceError as exc:
        raise HTTPException(422, str(exc)) from None
    # Add the connection metadata before committing/queuing the first job.
    return add_repository(
        db,
        user,
        "github",
        source,
        branch,
        selected["name"],
        github_repository_id=str(selected["id"]),
        github_connection_user_id=user.id,
    )
