import secrets
from datetime import timedelta

import pytest

from api.auth import digest
from api.client import load_session, origin, save_session
from api.db import utcnow
from api.models import AgentToken, AuthorizationRequest, User
from api.services.github_connection import challenge
from tests.conftest import register


def grant(client, write=False):
    verifier = secrets.token_urlsafe(48)
    result = client.post("/api/cli/device", json={"challenge": challenge(verifier), "write": write})
    assert result.status_code == 201
    d = result.json()
    code = d["user_code"]
    assert (
        client.post("/api/cli/device/" + code + "/approve", json={"approve": True}).status_code
        == 200
    )
    approved = client.post(
        "/api/cli/device/poll", json={"device_code": d["device_code"], "verifier": verifier}
    )
    assert approved.status_code == 200
    return approved.json(), d, verifier


def test_cli_scope_authorization_revocation_and_single_use(client, db):
    user = register(client)
    result, device, verifier = grant(client)
    assert "token" not in client.get("/api/cli/tokens").text
    token = result["token"]
    assert db.get(AgentToken, digest(token)).scopes == ["read"]
    client.headers["Authorization"] = "Bearer " + token
    assert client.get("/api/repositories").status_code == 200
    assert (
        client.post(
            "/api/repositories",
            json={"source_type": "github", "source": "https://github.com/pallets/itsdangerous"},
        ).status_code
        == 403
    )
    db.get(User, user["id"]).role = "admin"
    db.commit()
    assert client.get("/api/admin/users").status_code == 403
    assert client.post("/api/integrations/github/authorize").status_code == 403
    assert (
        client.post(
            "/api/cli/device/poll",
            json={"device_code": device["device_code"], "verifier": verifier},
        ).status_code
        == 410
    )
    assert client.post("/api/cli/logout").status_code == 200
    assert client.get("/api/repositories").status_code == 401


def test_cli_management_still_checks_repository_membership_and_browser_csrf(client, db):
    register(client)
    result, _, _ = grant(client, write=True)
    client.headers["Authorization"] = "Bearer " + result["token"]
    created = client.post(
        "/api/repositories",
        json={"source_type": "github", "source": "https://github.com/pallets/itsdangerous"},
    )
    assert created.status_code == 201
    repo_id = created.json()["repository"]["id"]
    del client.headers["Authorization"]
    register(client, "outsider@example.com")
    result, _, _ = grant(client, write=True)
    client.headers["Authorization"] = "Bearer " + result["token"]
    assert client.get("/api/repositories/" + repo_id).status_code == 404
    assert client.post("/api/repositories/" + repo_id + "/jobs").status_code == 404
    del client.headers["Authorization"]
    assert (
        client.post(
            "/api/repositories",
            headers={"X-CSRF-Token": "bad"},
            json={"source_type": "github", "source": "https://github.com/pallets/itsdangerous"},
        ).status_code
        == 403
    )


def test_cli_pending_verifier_poll_rate_and_expiry(client, db):
    register(client)
    verifier = secrets.token_urlsafe(48)
    d = client.post("/api/cli/device", json={"challenge": challenge(verifier)}).json()
    endpoint = "/api/cli/device/poll"
    assert (
        client.post(
            endpoint, json={"device_code": d["device_code"], "verifier": secrets.token_urlsafe(48)}
        ).status_code
        == 403
    )
    body = {"device_code": d["device_code"], "verifier": verifier}
    assert client.post(endpoint, json=body).status_code == 202
    assert client.post(endpoint, json=body).status_code == 429
    row = db.get(AuthorizationRequest, digest(d["device_code"]))
    row.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert client.post(endpoint, json=body).status_code == 410


def test_cli_files_are_private_and_server_origins_are_validated(tmp_path):
    path = tmp_path / "private" / "session.json"
    value = {"server": "https://graphpilot.example.com", "token": "gp_mcp_example"}
    save_session(path, value)
    assert load_session(path) == value
    path.chmod(0o644)
    with pytest.raises(ValueError):
        load_session(path)
    for bad in [
        "http://example.com",
        "https://user:password@example.com",
        "https://example.com/path",
        "https://example.com?token=private",
    ]:
        with pytest.raises(ValueError):
            origin(bad)


def test_registration_has_no_five_user_cap(client):
    for i in range(6):
        assert register(client, f"person{i}@example.com")["role"] == "user"


def test_actual_cli_commands_use_scoped_http_api(client, monkeypatch, tmp_path, capsys):
    import json
    from types import SimpleNamespace

    import httpx

    from api import client as cli

    user = register(client)
    issued, _, _ = grant(client, write=True)
    path = tmp_path / "session.json"
    save_session(path, {"server": "http://localhost:5173", "token": issued["token"]})

    def handle(request):
        headers = dict(request.headers)
        headers["Origin"] = "http://testserver"
        result = client.request(
            request.method, request.url.raw_path.decode(), headers=headers, content=request.content
        )
        return httpx.Response(
            result.status_code, content=result.content, headers={"Content-Type": "application/json"}
        )

    transport = httpx.MockTransport(handle)
    monkeypatch.setattr(
        cli,
        "httpx",
        SimpleNamespace(
            Client=lambda **kw: httpx.Client(transport=transport, **kw), HTTPError=httpx.HTTPError
        ),
    )

    def run(*args):
        monkeypatch.setattr("sys.argv", ["graphpilot", "--config", str(path), *args])
        assert cli.main() == 0
        return json.loads(capsys.readouterr().out)

    assert run("whoami")["id"] == user["id"]
    created = run("repos", "connect", "https://github.com/pallets/itsdangerous")
    repo_id = created["repository"]["id"]
    assert run("repos", "list")[0]["id"] == repo_id
    assert run("repos", "status", repo_id)["jobs"]
    checked = run("repos", "check", repo_id)
    assert "not executed" in checked["notice"]
    assert checked["recorded_ci"]["items"] == []
