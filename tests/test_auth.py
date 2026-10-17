from datetime import timedelta

from sqlalchemy import select

from api.auth import digest
from api.db import utcnow
from api.models import Audit, LoginSession, User
from tests.conftest import register


def test_register_login_logout_expiry_and_secret_redaction(client, db):
    user = register(client)
    assert client.get("/api/auth/session").json()["user"]["id"] == user["id"]
    serialized = client.get("/api/auth/session").text
    assert all(
        secret not in serialized for secret in ["password_hash", "database_url", "llm_api_key"]
    )
    assert client.cookies.get("gp_session") not in serialized
    assert db.get(User, user["id"]).password_hash.startswith("$argon2id$")
    assert (
        "HttpOnly"
        in client.post(
            "/api/auth/login", json={"email": user["email"], "password": "correct-horse-battery"}
        ).headers["set-cookie"]
    )
    client.headers["X-CSRF-Token"] = client.cookies["gp_csrf"]
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/session").status_code == 401
    assert (
        client.post(
            "/api/auth/login", json={"email": user["email"], "password": "wrong"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/auth/login", json={"email": user["email"], "password": "correct-horse-battery"}
        ).status_code
        == 200
    )
    session = db.get(LoginSession, digest(client.cookies["gp_session"]))
    session.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert client.get("/api/auth/session").status_code == 401


def test_csrf_origin_disabled_and_session_revoke(client, db):
    user = register(client)
    client.headers.pop("X-CSRF-Token")
    assert (
        client.patch("/api/auth/profile", json={"name": "Changed", "theme": "dark"}).status_code
        == 403
    )
    client.headers["X-CSRF-Token"] = "wrong"
    assert client.post("/api/auth/logout").status_code == 403
    client.headers["X-CSRF-Token"] = client.cookies["gp_csrf"]
    assert (
        client.patch(
            "/api/auth/profile",
            headers={"Origin": "https://evil.example"},
            json={"name": "Changed", "theme": "dark"},
        ).status_code
        == 403
    )
    assert (
        client.patch("/api/auth/profile", json={"name": "Changed", "theme": "dark"}).status_code
        == 200
    )
    db.get(User, user["id"]).disabled = True
    db.commit()
    assert client.get("/api/auth/session").status_code == 401
    assert (
        client.post(
            "/api/auth/login", json={"email": user["email"], "password": "correct-horse-battery"}
        ).status_code
        == 401
    )
    assert db.scalar(select(Audit).where(Audit.action == "account.update"))


def test_validation_duplicate_and_email_unavailable(client):
    assert (
        client.post(
            "/api/auth/register", json={"name": "", "email": "bad", "password": "short"}
        ).status_code
        == 422
    )
    register(client)
    assert (
        client.post(
            "/api/auth/register",
            json={"name": "Again", "email": "dev@example.com", "password": "correct-horse-battery"},
        ).status_code
        == 409
    )
    assert (
        client.post("/api/auth/password-reset", json={"email": "dev@example.com"}).status_code
        == 503
    )
    assert (
        client.post(
            "/api/auth/login",
            headers={"Origin": "https://evil.example"},
            json={"email": "dev@example.com", "password": "correct-horse-battery"},
        ).status_code
        == 403
    )


def test_revoke_session_and_logout_is_permanent(client, db):
    user = register(client)
    token = client.cookies["gp_session"]
    sessions = client.get("/api/auth/sessions").json()
    assert len(sessions) == 1 and sessions[0]["current"]
    assert client.delete("/api/auth/sessions/" + sessions[0]["id"]).status_code == 200
    assert db.get(LoginSession, digest(token)) is None
    assert client.get("/api/auth/session").status_code == 401
    assert user["role"] == "user"


def test_readiness_checks_real_databases(client):
    result = client.get("/api/health/ready")
    assert result.status_code == 200, result.text
    assert result.json()["checks"] == {"postgresql": "connected", "falkordb": "connected"}


def test_password_reset_delivery_one_time_and_revokes_sessions(client, db, monkeypatch):
    import re
    import smtplib

    from api.config import settings

    user = register(client)
    captured = []

    class Mail:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def starttls(self, *, context):
            import ssl

            assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED

        def send_message(self, message):
            captured.append(message)

    cfg = settings()
    original = (cfg.smtp_host, cfg.smtp_from)
    cfg.smtp_host, cfg.smtp_from = "mail.test", "GraphPilot <no-reply@example.com>"
    monkeypatch.setattr(smtplib, "SMTP", Mail)
    result = client.post("/api/auth/password-reset", json={"email": user["email"]})
    assert result.status_code == 200 and len(captured) == 1
    token = re.search(r"token=([\w-]+)", captured[0].get_content())[1]
    assert token not in result.text
    assert (
        client.post(
            "/api/auth/password-reset/confirm",
            json={"token": token, "password": "a-new-long-password"},
        ).status_code
        == 200
    )
    assert client.get("/api/auth/session").status_code == 401
    assert (
        client.post(
            "/api/auth/password-reset/confirm",
            json={"token": token, "password": "another-long-password"},
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/auth/login", json={"email": user["email"], "password": "a-new-long-password"}
        ).status_code
        == 200
    )
    cfg.smtp_host, cfg.smtp_from = original
