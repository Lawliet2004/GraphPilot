"""Real loopback SMTP/STARTTLS transactions; no external mail or mocked SMTP."""

import re
import ssl
from datetime import timedelta
from email import policy
from email.parser import BytesParser

import pytest
from aiosmtpd.controller import Controller
from aiosmtpd.smtp import AuthResult, LoginPassword
from sqlalchemy import select

from api.auth import digest
from api.config import settings
from api.db import utcnow
from api.models import Audit, PasswordReset
from scripts.verification_tls import certificate
from tests.conftest import register


class EphemeralSMTP(Controller):
    def _trigger_server(self):
        # Controller's readiness probe must use the OS-assigned port.
        self.port = self.server.sockets[0].getsockname()[1]
        super()._trigger_server()


class Mailbox:
    def __init__(self, reject=False):
        self.messages = []
        self.reject = reject

    async def handle_DATA(self, server, session, envelope):
        if self.reject:
            return "550 Test mailbox refused delivery"
        self.messages.append((session, envelope))
        return "250 Message accepted by local test mailbox"


def authenticate(server, session, envelope, mechanism, credentials):
    valid = isinstance(credentials, LoginPassword) and credentials == LoginPassword(
        b"smtp-test-user", b"smtp-test-password"
    )
    return AuthResult(success=valid, handled=False)


@pytest.fixture
def smtp_server(tmp_path, monkeypatch):
    controllers = []
    cfg = settings()

    def start(mode="trusted"):
        cert, key = certificate(
            tmp_path / mode,
            san="DNS:wrong-host.invalid" if mode == "wrong-hostname" else "IP:127.0.0.1",
        )
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(cert, key)
        mailbox = Mailbox(reject=mode == "recipient-rejected")
        server = EphemeralSMTP(
            mailbox,
            hostname="127.0.0.1",
            port=0,
            tls_context=None if mode == "no-starttls" else tls,
            require_starttls=True,
            auth_required=True,
            authenticator=authenticate,
        )
        server.start()
        controllers.append(server)
        monkeypatch.setattr(cfg, "smtp_host", "127.0.0.1")
        monkeypatch.setattr(cfg, "smtp_port", server.port)
        monkeypatch.setattr(cfg, "smtp_from", "GraphPilot <reset@example.invalid>")
        monkeypatch.setattr(cfg, "smtp_username", "smtp-test-user")
        monkeypatch.setattr(
            cfg, "smtp_password", "incorrect" if mode == "auth-rejected" else "smtp-test-password"
        )
        monkeypatch.setattr(cfg, "public_url", "https://graphpilot.example.invalid")
        if mode == "untrusted":
            other_cert, _ = certificate(tmp_path / "other-ca")
            monkeypatch.setenv("SSL_CERT_FILE", str(other_cert))
            monkeypatch.setenv("SSL_CERT_DIR", str(tmp_path / "no-system-certs"))
        else:
            monkeypatch.setenv("SSL_CERT_FILE", str(cert))
        return mailbox

    yield start
    for server in reversed(controllers):
        server.stop()


def test_real_starttls_authenticated_reset_delivery(client, db, smtp_server):
    user = register(client)
    mailbox = smtp_server()
    response = client.post("/api/auth/password-reset", json={"email": user["email"]})
    assert response.status_code == 200
    assert len(mailbox.messages) == 1
    session, envelope = mailbox.messages[0]
    assert session.ssl and session.authenticated
    assert envelope.mail_from == "reset@example.invalid"
    assert envelope.rcpt_tos == [user["email"]]
    message = BytesParser(policy=policy.default).parsebytes(envelope.original_content)
    assert message["Subject"] == "Reset your GraphPilot password"
    content = message.get_content()
    token = re.search(r"token=([\w-]+)", content)[1]
    assert "https://graphpilot.example.invalid/reset-password?token=" in content
    assert token not in response.text
    assert db.get(PasswordReset, digest(token)) is not None
    assert (
        client.post(
            "/api/auth/password-reset/confirm",
            json={"token": token, "password": "changed-after-real-smtp"},
        ).status_code
        == 200
    )
    assert client.get("/api/auth/session").status_code == 401
    assert (
        client.post(
            "/api/auth/password-reset/confirm",
            json={"token": token, "password": "second-reset-must-fail"},
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/auth/login", json={"email": user["email"], "password": "changed-after-real-smtp"}
        ).status_code
        == 200
    )
    unknown = client.post("/api/auth/password-reset", json={"email": "unknown@example.invalid"})
    assert unknown.json() == response.json()
    assert len(mailbox.messages) == 1


@pytest.mark.parametrize(
    "mode", ["no-starttls", "untrusted", "wrong-hostname", "auth-rejected", "recipient-rejected"]
)
def test_real_smtp_failures_preserve_prior_token_and_session(client, db, smtp_server, mode):
    user = register(client)
    prior = digest("prior-valid-reset-token")
    db.add(PasswordReset(id=prior, user_id=user["id"], expires_at=utcnow() + timedelta(minutes=5)))
    db.commit()
    mailbox = smtp_server(mode)
    response = client.post("/api/auth/password-reset", json={"email": user["email"]})
    assert response.status_code == 503
    assert response.json() == {"detail": "Email delivery is temporarily unavailable"}
    assert mailbox.messages == []
    db.expire_all()
    assert [row.id for row in db.scalars(select(PasswordReset))] == [prior]
    assert db.scalar(select(Audit).where(Audit.action == "account.reset_requested")) is None
    assert client.get("/api/auth/session").status_code == 200
