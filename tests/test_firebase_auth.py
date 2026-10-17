import json
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


@pytest.fixture
def provider(monkeypatch):
    cfg = settings()
    monkeypatch.setattr(cfg, "firebase_project_id", "demo-graphpilot")
    monkeypatch.setattr(cfg, "firebase_api_key", "test-api-key")
    state = {"users": {}, "emails": [], "error": None}

    def handle(request):
        assert request.url.scheme == "https"
        assert request.url.host == "identitytoolkit.googleapis.com"
        assert request.url.params["key"] == "test-api-key"
        body = json.loads(request.content)
        action = request.url.path.rsplit(":", 1)[1]

        def error(code, status=400):
            return httpx.Response(status, json={"error": {"message": code}})

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
            return httpx.Response(
                200,
                json={
                    "localId": row["localId"],
                    "idToken": "test-token-" + row["localId"],
                    "expiresIn": "3600",
                },
            )
        if action == "lookup":
            row = next(
                (
                    r
                    for r in state["users"].values()
                    if "test-token-" + r["localId"] == body["idToken"]
                ),
                None,
            )
            if not row:
                return error("INVALID_ID_TOKEN")
            return httpx.Response(
                200, json={"users": [{**row, "passwordHash": "private-provider-hash"}]}
            )
        if action == "sendOobCode":
            state["emails"].append(body)
            if body.get("email") and body["email"] not in state["users"]:
                return error("EMAIL_NOT_FOUND")
            return httpx.Response(200, json={})
        raise AssertionError("Unexpected Firebase operation")

    transport = httpx.MockTransport(handle)
    monkeypatch.setattr(
        firebase_auth,
        "httpx",
        SimpleNamespace(
            Client=lambda **kw: httpx.Client(transport=transport, **kw), HTTPError=httpx.HTTPError
        ),
    )
    return state


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
    assert client.get("/api/auth/session").json()["email_verified"]
    row = db.get(LoginSession, digest(client.cookies["gp_session"]))
    assert row.expires_at <= utcnow() + timedelta(hours=1)
    assert client.post("/api/auth/logout").status_code == 200
    assert not client.cookies.get("gp_firebase")
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
    assert client.get("/api/auth/session").status_code == 401


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
