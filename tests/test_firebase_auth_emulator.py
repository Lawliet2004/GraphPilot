"""Opt-in check against the official, loopback-only Firebase Auth emulator."""

import os
import time
import uuid

import httpx
import pytest

from api.auth import digest
from api.config import settings
from api.models import LoginSession

pytestmark = pytest.mark.skipif(
    os.getenv("GP_TEST_FIREBASE_EMULATOR") != "1",
    reason="Start the Firebase Auth emulator on 127.0.0.1:19099 and explicitly opt in",
)


def test_real_firebase_email_verification_reset_and_revocation(client, db, monkeypatch):
    cfg = settings()
    monkeypatch.setattr(cfg, "firebase_project_id", "demo-graphpilot")
    monkeypatch.setattr(cfg, "firebase_api_key", "emulator-only-key")
    monkeypatch.setattr(cfg, "firebase_emulator_host", "127.0.0.1:19099")
    email = f"emulator-{uuid.uuid4().hex}@example.com"
    password = "emulator-only-password"
    result = client.post(
        "/api/auth/register", json={"name": "Emulator demo", "email": email, "password": password}
    )
    assert result.status_code == 201, result.text
    client.headers["X-CSRF-Token"] = result.json()["csrf"]
    assert result.json()["user"]["role"] == "user"
    assert client.get("/api/admin/users").status_code == 403
    assert client.get("/api/auth/session").json()["email_verified"] is False

    with httpx.Client(base_url="http://127.0.0.1:19099", trust_env=False) as emulator:
        codes_url = "/emulator/v1/projects/demo-graphpilot/oobCodes"
        codes = emulator.get(codes_url).json()["oobCodes"]
        verify = next(c for c in reversed(codes) if c["email"] == email)
        verified = emulator.post(
            "/identitytoolkit.googleapis.com/v1/accounts:update?key=emulator-only-key",
            json={"oobCode": verify["oobCode"]},
        )
        assert verified.status_code == 200
        assert client.get("/api/auth/session").json()["email_verified"] is True
        # Firebase's revocation timestamps have one-second granularity.
        session = db.get(LoginSession, digest(client.cookies["gp_session"]))
        time.sleep(max(0, session.created_at.timestamp() + 1.1 - time.time()))
        reset = client.post("/api/auth/password-reset", json={"email": email})
        assert reset.status_code == 200
        codes = emulator.get(codes_url).json()["oobCodes"]
        reset_code = next(
            c
            for c in reversed(codes)
            if c["email"] == email and c["requestType"] == "PASSWORD_RESET"
        )
        changed = emulator.post(
            "/identitytoolkit.googleapis.com/v1/accounts:resetPassword?key=emulator-only-key",
            json={"oobCode": reset_code["oobCode"], "newPassword": password + "-changed"},
        )
        assert changed.status_code == 200
    assert client.get("/api/auth/session").status_code == 401
    assert (
        client.post("/api/auth/login", json={"email": email, "password": password}).status_code
        == 401
    )
    signed_in = client.post(
        "/api/auth/login", json={"email": email, "password": password + "-changed"}
    )
    assert signed_in.status_code == 200
    client.headers["X-CSRF-Token"] = signed_in.json()["csrf"]
    assert client.get("/api/auth/session").json()["email_verified"] is True
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/session").status_code == 401
