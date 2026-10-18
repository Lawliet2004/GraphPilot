import base64
import json
import time
import urllib.parse
from datetime import timedelta
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from api.auth import digest
from api.config import Settings, settings
from api.db import utcnow
from api.models import LoginSession, User
from api.services import firebase_auth
from tests.conftest import register


def fake_jwt(uid, exp):
    payload = base64.urlsafe_b64encode(json.dumps({"sub": uid, "exp": exp}).encode())
    return "header." + payload.decode().rstrip("=") + ".signature"


def jwt_exp(token):
    return json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))["exp"]


def set_cookie(client, name, value):
    client.cookies.set(name, value, domain="testserver.local", path="/")


@pytest.fixture
def provider(monkeypatch):
    cfg = settings()
    monkeypatch.setattr(cfg, "firebase_project_id", "demo-graphpilot")
    monkeypatch.setattr(cfg, "firebase_api_key", "test-api-key")
    firebase_auth.clear_cache()
    state = {
        "users": {},
        "emails": [],
        "error": None,
        "tokens": {},
        "refresh": {},
        "lookups": 0,
        "refreshes": 0,
        "issued": 0,
    }

    def issue(uid):
        state["issued"] += 1
        token = fake_jwt(uid, int(time.time()) + 3600 + state["issued"])
        state["tokens"][token] = uid
        return token

    def by_uid(uid):
        return next(r for r in state["users"].values() if r["localId"] == uid)

    def handle(request):
        assert request.url.scheme == "https"
        assert request.url.host in {
            "identitytoolkit.googleapis.com",
            "securetoken.googleapis.com",
        }
        assert request.url.params["key"] == "test-api-key"
        if request.url.host == "securetoken.googleapis.com":
            form = urllib.parse.parse_qs(request.content.decode())
            assert form["grant_type"] == ["refresh_token"]
            state["refreshes"] += 1
            uid = state["refresh"].get(form["refresh_token"][0])
            if not uid:
                return error("INVALID_REFRESH_TOKEN")
            if by_uid(uid)["disabled"]:
                return error("USER_DISABLED")
            return httpx.Response(
                200,
                json={
                    "id_token": issue(uid),
                    "refresh_token": form["refresh_token"][0],
                    "expires_in": "3600",
                },
            )
        body = json.loads(request.content)
        action = request.url.path.rsplit(":", 1)[1]

        if state["error"]:
            return error(*state["error"])
        if action in {"signUp", "signInWithPassword"}:
            email = body["email"].lower()
            row = state["users"].get(email)
            if action == "signUp":
                if row:
                    return error("EMAIL_EXISTS")
                row = {
                    "localId": f"uid-{len(state['users'])}",
                    "email": email,
                    "password": body["password"],
                    "emailVerified": False,
                    "validSince": "0",
                    "disabled": False,
                    "customClaims": {"role": "admin"},
                }
                state["users"][email] = row
            elif not row or row["password"] != body["password"]:
                return error("INVALID_LOGIN_CREDENTIALS")
            if row["disabled"]:
                return error("USER_DISABLED")
            refresh = f"refresh-{row['localId']}-{len(state['refresh'])}"
            state["refresh"][refresh] = row["localId"]
            return httpx.Response(
                200,
                json={
                    "localId": row["localId"],
                    "idToken": issue(row["localId"]),
                    "refreshToken": refresh,
                    "expiresIn": "3600",
                },
            )
        if action == "lookup":
            state["lookups"] += 1
            uid = state["tokens"].get(body["idToken"])
            if not uid:
                return error("INVALID_ID_TOKEN")
            if jwt_exp(body["idToken"]) <= time.time():
                return error("TOKEN_EXPIRED")
            return httpx.Response(
                200, json={"users": [{**by_uid(uid), "passwordHash": "private-provider-hash"}]}
            )
        if action == "sendOobCode":
            state["emails"].append(body)
            if body.get("email") and body["email"] not in state["users"]:
                return error("EMAIL_NOT_FOUND")
            return httpx.Response(200, json={})
        raise AssertionError("Unexpected Firebase operation")

    def error(code, status=400):
        return httpx.Response(status, json={"error": {"message": code}})

    transport = httpx.MockTransport(handle)
    monkeypatch.setattr(
        firebase_auth,
        "httpx",
        SimpleNamespace(
            Client=httpx.Client,
            HTTPTransport=lambda **kw: transport,
            HTTPError=httpx.HTTPError,
        ),
    )
    yield state
    firebase_auth.clear_cache()


def signup(client, email="managed@example.com"):
    result = client.post(
        "/api/auth/register",
        json={"name": "Managed user", "email": email, "password": "strong-managed-password"},
    )
    assert result.status_code == 201, result.text
    client.headers["X-CSRF-Token"] = result.json()["csrf"]
    return result


def test_managed_registration_session_permissions_verification_and_logout(client, db, provider):
    result = signup(client)
    user = db.get(User, result.json()["user"]["id"])
    assert user.password_hash == "!firebase" and user.firebase_identity == "demo-graphpilot:uid-0"
    assert result.json()["user"]["role"] == "user"  # Ignore provider/client role metadata.
    assert result.json()["verification_email_sent"]
    assert provider["emails"][0]["requestType"] == "VERIFY_EMAIL"
    assert "gp_firebase=" in result.headers["set-cookie"]
    assert "gp_firebase_refresh=" in result.headers["set-cookie"]
    session = client.get("/api/auth/session")
    assert session.json()["auth_provider"] == "firebase" and not session.json()["email_verified"]
    assert all(
        x not in session.text
        for x in ["test-token", "passwordHash", "firebase_identity", "private-provider-hash"]
    )
    assert client.get("/api/admin/users").status_code == 403
    assert (
        client.post("/api/auth/email-verification", headers={"X-CSRF-Token": "wrong"}).status_code
        == 403
    )
    assert client.post("/api/auth/email-verification").status_code == 200
    provider["users"][user.email]["emailVerified"] = True
    firebase_auth.clear_cache()
    assert client.get("/api/auth/session").json()["email_verified"]
    row = db.get(LoginSession, digest(client.cookies["gp_session"]))
    assert row.expires_at > utcnow() + timedelta(hours=1)
    assert client.post("/api/auth/logout").status_code == 200
    assert not client.cookies.get("gp_firebase")
    assert not client.cookies.get("gp_firebase_refresh")
    assert client.get("/api/auth/session").status_code == 401


@pytest.mark.parametrize(
    "restriction", ["disabled", "revoked", "wrong_identity", "no_provider_cookie"]
)
def test_provider_changes_are_checked_on_existing_sessions(client, provider, restriction):
    signup(client)
    row = provider["users"]["managed@example.com"]
    if restriction == "disabled":
        row["disabled"] = True
    elif restriction == "revoked":
        row["validSince"] = str(int((utcnow() + timedelta(minutes=1)).timestamp()))
    elif restriction == "wrong_identity":
        client.cookies.set("gp_firebase", "unknown-identity")
    else:
        client.cookies.delete("gp_firebase")
    firebase_auth.clear_cache()
    assert client.get("/api/auth/session").status_code == 401


def test_expired_id_token_refreshes_once_and_renews_cookies(client, provider):
    signup(client)
    uid = provider["users"]["managed@example.com"]["localId"]
    expired = fake_jwt(uid, int(time.time()) - 5)
    provider["tokens"][expired] = uid
    set_cookie(client, "gp_firebase", expired)
    response = client.get("/api/auth/session")
    assert response.status_code == 200
    cookies = response.headers.get_list("set-cookie")
    renewed = next(c for c in cookies if c.startswith("gp_firebase=") and "Max-Age=604800" in c)
    renewed = renewed.split(";")[0].split("=", 1)[1]
    assert renewed != expired and jwt_exp(renewed) > time.time()
    assert any(c.startswith("gp_firebase_refresh=") and "Max-Age=604800" in c for c in cookies)
    assert provider["refreshes"] == 1
    assert client.get("/api/auth/session").status_code == 200
    assert provider["refreshes"] == 1


def test_failed_or_unneeded_refresh_ends_the_session(client, provider):
    signup(client)
    uid = provider["users"]["managed@example.com"]["localId"]
    expired = fake_jwt(uid, int(time.time()) - 5)
    provider["tokens"][expired] = uid
    set_cookie(client, "gp_firebase", expired)
    set_cookie(client, "gp_firebase_refresh", "revoked-refresh-credential")
    assert client.get("/api/auth/session").status_code == 401
    assert provider["refreshes"] == 1
    set_cookie(client, "gp_firebase", "not-a-token")
    assert client.get("/api/auth/session").status_code == 401
    assert provider["refreshes"] == 1


def test_disabled_account_is_not_renewed(client, provider):
    signup(client)
    user = provider["users"]["managed@example.com"]
    expired = fake_jwt(user["localId"], int(time.time()) - 5)
    provider["tokens"][expired] = user["localId"]
    user["disabled"] = True
    set_cookie(client, "gp_firebase", expired)
    assert client.get("/api/auth/session").status_code == 401


def test_account_lookups_are_cached_for_a_short_ttl(client, provider):
    signup(client)
    before = provider["lookups"]
    for _ in range(3):
        assert client.get("/api/auth/session").status_code == 200
    assert provider["lookups"] - before == 1


def test_account_cache_is_bounded(provider, monkeypatch):
    monkeypatch.setattr(firebase_auth, "ACCOUNT_CACHE_LIMIT", 2)
    tokens = []
    for i in range(3):
        signed = firebase_auth.password_sign_in(
            f"cache{i}@example.com", "strong-managed-password", create=True
        )
        tokens.append(signed["id_token"])
    for token in tokens:
        firebase_auth.account(token)
    assert len(firebase_auth._accounts) == 2


def test_existing_native_account_is_not_automatically_linked_by_email(client, db, monkeypatch):
    original = register(client, "owner@example.com")
    user = db.get(User, original["id"])
    user.role = "admin"
    db.commit()
    monkeypatch.setattr(settings(), "firebase_project_id", "demo-graphpilot")
    monkeypatch.setattr(settings(), "firebase_api_key", "test-key")
    monkeypatch.setattr(
        firebase_auth,
        "password_sign_in",
        lambda *a, **kw: {"id_token": "provider-token", "expires_in": 3600},
    )
    monkeypatch.setattr(
        firebase_auth,
        "account",
        lambda token: {"identity": "demo-graphpilot:external", "email": user.email},
    )
    # An identity whose email collides cannot inherit an existing administrator.
    result = client.post(
        "/api/auth/login", json={"email": "alias@example.com", "password": "anything"}
    )
    assert result.status_code == 409
    assert db.get(User, original["id"]).firebase_identity is None
    assert (
        client.post(
            "/api/auth/login", json={"email": user.email, "password": "correct-horse-battery"}
        ).status_code
        == 200
    )


def test_managed_account_never_falls_back_to_native_password(client, db, provider, monkeypatch):
    result = signup(client)
    user = db.get(User, result.json()["user"]["id"])
    from api.auth import password_hasher

    user.password_hash = password_hasher.hash("legacy-password-still-present")
    db.commit()
    assert (
        client.post(
            "/api/auth/login",
            json={"email": user.email, "password": "legacy-password-still-present"},
        ).status_code
        == 401
    )
    monkeypatch.setattr(settings(), "firebase_api_key", "")
    assert (
        client.post(
            "/api/auth/login",
            json={"email": user.email, "password": "legacy-password-still-present"},
        ).status_code
        == 503
    )


def test_first_signin_provisions_only_normal_user_and_native_disable_wins(client, db, provider):
    firebase_auth.password_sign_in(
        "console-user@example.com", "strong-managed-password", create=True
    )
    result = client.post(
        "/api/auth/login",
        json={"email": "console-user@example.com", "password": "strong-managed-password"},
    )
    assert result.status_code == 200 and result.json()["user"]["role"] == "user"
    user = db.scalar(select(User).where(User.email == "console-user@example.com"))
    user.disabled = True
    db.commit()
    assert client.get("/api/auth/session").status_code == 401
    assert (
        client.post(
            "/api/auth/login", json={"email": user.email, "password": "strong-managed-password"}
        ).status_code
        == 401
    )


def test_reset_hides_unknown_accounts_and_provider_errors_are_sanitized(client, provider):
    known = client.post("/api/auth/password-reset", json={"email": "unknown@example.com"})
    assert known.status_code == 200
    provider["error"] = ("private-provider-token-and-error", 500)
    failed = client.post(
        "/api/auth/login", json={"email": "unknown@example.com", "password": "anything"}
    )
    assert failed.status_code == 503 and "private-provider" not in failed.text
    provider["error"] = ("QUOTA_EXCEEDED", 429)
    assert (
        client.post("/api/auth/password-reset", json={"email": "unknown@example.com"}).status_code
        == 429
    )


def test_registration_survives_email_quota_failure(client, provider, monkeypatch):
    def failed(token):
        raise HTTPException(429, "Email quota exhausted")

    monkeypatch.setattr(firebase_auth, "send_verification", failed)
    result = signup(client)
    assert result.json()["verification_email_sent"] is False
    assert client.get("/api/auth/session").status_code == 200


def test_firebase_emulator_never_allowed_in_production():
    for values in [
        {"environment": "production", "firebase_emulator_host": "127.0.0.1:9099"},
        {"firebase_emulator_host": "public.example:9099"},
        {"firebase_project_id": "demo-graphpilot", "firebase_api_key": ""},
    ]:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **values)


def test_explicit_operator_link_preserves_admin_and_revokes_old_credentials(
    client, db, monkeypatch
):
    from api import cli
    from api.services.agent_tokens import issue_token

    original = register(client, "migrate-admin@example.com")
    user = db.get(User, original["id"])
    user.role = "admin"
    _, agent = issue_token(db, user, "Before migration")
    agent_id = agent.id
    old_session = digest(client.cookies["gp_session"])
    db.commit()
    monkeypatch.setattr(settings(), "firebase_project_id", "demo-graphpilot")
    monkeypatch.setattr(settings(), "firebase_api_key", "test-key")
    monkeypatch.setattr("sys.argv", ["graphpilot", "link-firebase", user.email, "verified-uid"])
    cli.main()
    db.expire_all()
    linked = db.get(User, original["id"])
    assert linked.role == "admin" and linked.firebase_identity == "demo-graphpilot:verified-uid"
    assert db.get(LoginSession, old_session) is None
    from api.models import AgentToken

    assert db.get(AgentToken, agent_id).revoked_at is not None
    assert client.get("/api/auth/session").status_code == 401
