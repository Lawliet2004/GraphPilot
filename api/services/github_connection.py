"""Per-user, encrypted GitHub App credentials. Never inherit a server owner's token."""

import base64
import hashlib
from datetime import timedelta

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException

from api.config import settings
from api.db import SessionLocal, utcnow
from api.models import GitHubConnection


def enabled():
    c = settings()
    return bool(
        c.github_client_id and c.github_client_secret and c.github_app_slug and c.credential_key
    )


def cipher():
    if not settings().credential_key:
        raise HTTPException(503, "GitHub connection encryption is not configured")
    return Fernet(settings().credential_key.encode())


def seal(value):
    return cipher().encrypt(value.encode()).decode()


def unseal(value):
    try:
        return cipher().decrypt(value.encode()).decode()
    except (InvalidToken, ValueError):
        raise HTTPException(
            503, "GitHub connection credentials need administrator attention"
        ) from None


def challenge(verifier):
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")


def request(method, path, *, token=None, body=None, oauth=False, params=None):
    if not path.startswith("/") or "://" in path or ".." in path:
        raise ValueError("Invalid GitHub API path")
    headers = {
        "Accept": "application/json" if oauth else "application/vnd.github+json",
        "User-Agent": "GraphPilot/0.1",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    if not oauth:
        headers["X-GitHub-Api-Version"] = "2026-03-10"
    origin = "https://github.com" if oauth else "https://api.github.com"
    try:
        with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client:
            response = client.request(
                method, origin + path, headers=headers, json=body, params=params
            )
        data = response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, "GitHub is temporarily unavailable. Try again.") from None
    if response.status_code in {401, 403, 404} or isinstance(data, dict) and data.get("error"):
        raise HTTPException(
            403, "GitHub access is unavailable. Reconnect and check selected repositories."
        )
    if response.status_code != 200:
        raise HTTPException(503, "GitHub could not complete the request")
    return data


def oauth(body):
    c = settings()
    result = request(
        "POST",
        "/login/oauth/access_token",
        oauth=True,
        body={"client_id": c.github_client_id, "client_secret": c.github_client_secret, **body},
    )
    if (
        not isinstance(result, dict)
        or not isinstance(result.get("access_token"), str)
        or not result["access_token"].startswith("ghu_")
    ):
        raise HTTPException(403, "A GitHub App user authorization is required")
    return result


def update_tokens(row, result):
    row.access_token = seal(result["access_token"])
    if result.get("refresh_token"):
        row.refresh_token = seal(result["refresh_token"])
    row.expires_at = (
        utcnow() + timedelta(seconds=int(result["expires_in"]))
        if result.get("expires_in")
        else None
    )


def token_for(user_id):
    if not enabled():
        raise HTTPException(503, "GitHub App is not configured")
    # Serialize refresh-token rotation across API and worker processes.
    from sqlalchemy import select

    with SessionLocal() as db:
        row = db.scalar(
            select(GitHubConnection).where(GitHubConnection.user_id == user_id).with_for_update()
        )
        if not row:
            raise HTTPException(403, "Connect your GitHub account first")
        if row.expires_at and row.expires_at <= utcnow() + timedelta(minutes=2):
            if not row.refresh_token:
                raise HTTPException(403, "GitHub authorization expired. Reconnect your account.")
            result = oauth(
                {"grant_type": "refresh_token", "refresh_token": unseal(row.refresh_token)}
            )
            update_tokens(row, result)
            db.commit()
        return unseal(row.access_token)


def installations(token):
    result = request("GET", "/user/installations", token=token, params={"per_page": 100})
    return result.get("installations", [])


def repositories(token, installation_id, page=1):
    allowed = {int(i["id"]) for i in installations(token)}
    if installation_id not in allowed:
        raise HTTPException(404, "GitHub installation not found")
    result = request(
        "GET",
        f"/user/installations/{installation_id}/repositories",
        token=token,
        params={"per_page": 100, "page": page},
    )
    return result.get("repositories", []), int(result.get("total_count", 0))


def repository_token(user_id, repository_id):
    token = token_for(user_id)
    result = request("GET", f"/repositories/{int(repository_id)}", token=token)
    if str(result.get("id")) != str(repository_id):
        raise HTTPException(403, "GitHub repository access changed")
    return token
