"""Firebase's official Auth REST API, with no service-account key or browser SDK.

Credentials go only to Google's fixed HTTPS endpoint. Firebase owns passwords;
GraphPilot keeps HttpOnly sessions and its own role/repository permissions.
"""

import logging

import httpx
from fastapi import HTTPException

from api.config import settings

logging.getLogger("httpx").setLevel(logging.WARNING)


def enabled():
    return bool(settings().firebase_project_id and settings().firebase_api_key)


def identity(uid):
    if not isinstance(uid, str) or not 1 <= len(uid) <= 128:
        raise HTTPException(503, "Authentication provider returned an invalid identity")
    return settings().firebase_project_id + ":" + uid


def call(action, body):
    cfg = settings()
    if not enabled():
        raise HTTPException(503, "Firebase authentication is not configured")
    # Settings rejects public/emulator URLs and any production emulator use.
    base = (
        f"http://{cfg.firebase_emulator_host}/identitytoolkit.googleapis.com/v1/"
        if cfg.firebase_emulator_host
        else "https://identitytoolkit.googleapis.com/v1/"
    )
    try:
        with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as http:
            result = http.post(
                base + "accounts:" + action, params={"key": cfg.firebase_api_key}, json=body
            )
        data = result.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, "Authentication provider is temporarily unavailable") from None
    if not isinstance(data, dict):
        raise HTTPException(503, "Authentication provider returned an invalid response")
    if result.status_code != 200:
        error = data.get("error", {})
        code = error.get("message", "") if isinstance(error, dict) else ""
        if code == "EMAIL_EXISTS":
            raise HTTPException(409, "An account with that email already exists")
        if code in {"INVALID_EMAIL", "MISSING_PASSWORD", "WEAK_PASSWORD"} or str(code).startswith(
            "WEAK_PASSWORD :"
        ):
            raise HTTPException(422, "Use a valid email and a stronger password")
        if code in {"TOO_MANY_ATTEMPTS_TRY_LATER", "QUOTA_EXCEEDED"} or result.status_code == 429:
            raise HTTPException(429, "Too many attempts. Please try again later.")
        if code in {
            "INVALID_LOGIN_CREDENTIALS",
            "EMAIL_NOT_FOUND",
            "INVALID_PASSWORD",
            "USER_DISABLED",
            "INVALID_ID_TOKEN",
            "TOKEN_EXPIRED",
            "USER_NOT_FOUND",
            "CREDENTIAL_TOO_OLD_LOGIN_AGAIN",
        }:
            raise HTTPException(401, "Email or password is incorrect, or the session has expired")
        # Never relay provider response text, URLs, tokens or request bodies.
        raise HTTPException(503, "Authentication provider is temporarily unavailable")
    return data


def password_sign_in(email, password, *, create=False):
    result = call(
        "signUp" if create else "signInWithPassword",
        {"email": email, "password": password, "returnSecureToken": True},
    )
    uid = result.get("localId")
    token = result.get("idToken")
    identity(uid)
    if not isinstance(token, str) or not 1 <= len(token) <= 3800:
        raise HTTPException(503, "Authentication provider returned an invalid session")
    try:
        expires = min(3600, max(1, int(result["expiresIn"])))
    except (KeyError, TypeError, ValueError):
        raise HTTPException(503, "Authentication provider returned an invalid session") from None
    return {"uid": uid, "id_token": token, "expires_in": expires}


def account(token):
    if not token or len(token) > 3800:
        raise HTTPException(401, "Please log in to continue")
    result = call("lookup", {"idToken": token})
    rows = result.get("users", [])
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise HTTPException(401, "Please log in to continue")
    row = rows[0]
    if row.get("disabled") or not row.get("email"):
        raise HTTPException(401, "Please log in to continue")
    try:
        valid_since = int(row.get("validSince", "0"))
    except (TypeError, ValueError):
        raise HTTPException(503, "Authentication provider returned an invalid session") from None
    # In particular, never expose the provider's passwordHash/userInfo fields.
    return {
        "identity": identity(row.get("localId")),
        "email": str(row["email"]).lower(),
        "email_verified": row.get("emailVerified") is True,
        "valid_since": valid_since,
    }


def send_verification(token):
    call("sendOobCode", {"requestType": "VERIFY_EMAIL", "idToken": token})


def send_password_reset(email):
    try:
        call("sendOobCode", {"requestType": "PASSWORD_RESET", "email": email})
    except HTTPException as exc:
        # Hide whether the account exists, including projects without enumeration protection.
        if exc.status_code != 401:
            raise
