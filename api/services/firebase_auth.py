"""Firebase's official Auth REST API, with no service-account key or browser SDK.

Credentials go only to Google's fixed HTTPS endpoint. Firebase owns passwords;
GraphPilot keeps HttpOnly sessions and its own role/repository permissions.
"""

import base64
import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict

import httpx
from fastapi import HTTPException

from api.config import settings

logging.getLogger("httpx").setLevel(logging.WARNING)
ACCOUNT_TTL_SECONDS = 60
ACCOUNT_CACHE_LIMIT = 1024
SESSION_EXPIRED = "Please log in to continue"
_accounts = OrderedDict()
_accounts_lock = threading.Lock()


def enabled():
    return bool(settings().firebase_project_id and settings().firebase_api_key)


def identity(uid):
    if not isinstance(uid, str) or not 1 <= len(uid) <= 128:
        raise HTTPException(503, "Authentication provider returned an invalid identity")
    return settings().firebase_project_id + ":" + uid


def provider(service, path, *, body=None, form=None):
    cfg = settings()
    if not enabled():
        raise HTTPException(503, "Firebase authentication is not configured")
    # Settings rejects public/emulator URLs and any production emulator use.
    base = (
        f"http://{cfg.firebase_emulator_host}/{service}/v1/"
        if cfg.firebase_emulator_host
        else f"https://{service}/v1/"
    )
    try:
        # Some demo networks advertise IPv6 without a working route to Google.
        # Bind outbound Auth requests to IPv4 rather than stalling on each address.
        with httpx.Client(
            timeout=15,
            follow_redirects=False,
            trust_env=False,
            transport=httpx.HTTPTransport(
                local_address=None if cfg.firebase_emulator_host else "0.0.0.0"
            ),
        ) as http:
            result = http.post(
                base + path, params={"key": cfg.firebase_api_key}, json=body, data=form
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
            "INVALID_REFRESH_TOKEN",
        }:
            raise HTTPException(401, "Email or password is incorrect, or the session has expired")
        # Never relay provider response text, URLs, tokens or request bodies.
        raise HTTPException(503, "Authentication provider is temporarily unavailable")
    return data


def call(action, body):
    return provider("identitytoolkit.googleapis.com", "accounts:" + action, body=body)


def lifetime(value):
    try:
        return min(3600, max(1, int(value)))
    except (TypeError, ValueError):
        raise HTTPException(503, "Authentication provider returned an invalid session") from None


def refresh_credential(value):
    return value if isinstance(value, str) and 1 <= len(value) <= 2000 else None


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
    expires = lifetime(result.get("expiresIn"))
    return {
        "uid": uid,
        "id_token": token,
        "expires_in": expires,
        "refresh_token": refresh_credential(result.get("refreshToken")),
    }


def refresh(refresh_token):
    if not refresh_credential(refresh_token):
        raise HTTPException(401, SESSION_EXPIRED)
    try:
        result = provider(
            "securetoken.googleapis.com",
            "token",
            form={"grant_type": "refresh_token", "refresh_token": refresh_token},
        )
        token = result.get("id_token")
        if not isinstance(token, str) or not 1 <= len(token) <= 3800:
            raise HTTPException(503, "Authentication provider returned an invalid session")
        return {
            "id_token": token,
            "refresh_token": refresh_credential(result.get("refresh_token")) or refresh_token,
            "expires_in": lifetime(result.get("expires_in")),
        }
    except HTTPException:
        raise HTTPException(401, SESSION_EXPIRED) from None


def expired(token):
    try:
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return claims["exp"] <= time.time()
    except (IndexError, KeyError, TypeError, ValueError):
        return False


def session_account(id_token, refresh_token):
    """Return (account, renewed credentials). Refresh only a genuinely expired id token."""
    try:
        return account(id_token), None
    except HTTPException as exc:
        if exc.status_code != 401 or not expired(id_token):
            raise
    renewed = refresh(refresh_token)
    return account(renewed["id_token"]), renewed


def clear_cache():
    with _accounts_lock:
        _accounts.clear()


def account(token):
    if not token or len(token) > 3800:
        raise HTTPException(401, SESSION_EXPIRED)
    key = hashlib.sha256(token.encode()).hexdigest()
    now = time.monotonic()
    with _accounts_lock:
        cached = _accounts.get(key)
        if cached and cached[0] > now:
            return cached[1]
    result = lookup(token)
    with _accounts_lock:
        _accounts[key] = (now + ACCOUNT_TTL_SECONDS, result)
        _accounts.move_to_end(key)
        while len(_accounts) > ACCOUNT_CACHE_LIMIT:
            _accounts.popitem(last=False)
    return result


def lookup(token):
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
