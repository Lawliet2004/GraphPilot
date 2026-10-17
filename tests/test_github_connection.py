import json
from datetime import timedelta
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from api.config import settings
from api.db import utcnow
from api.models import GitHubConnection, Repository
from api.services import github_connection as gh
from tests.conftest import register


@pytest.fixture
def github(monkeypatch):
    for name, value in {
        "github_client_id": "Iv1.test",
        "github_client_secret": "private-client-secret",
        "github_app_slug": "graphpilot-test",
        "credential_key": Fernet.generate_key().decode(),
    }.items():
        monkeypatch.setattr(settings(), name, value)
    state = {"error": False, "refreshes": 0, "calls": []}

    def handler(request):
        state["calls"].append(request)
        if state["error"]:
            return httpx.Response(401, json={"message": "provider-secret-value"})
        if request.url.host == "github.com":
            body = json.loads(request.content)
            assert body["client_secret"] == "private-client-secret"
            if body.get("grant_type") == "refresh_token":
                state["refreshes"] += 1
            else:
                assert body["code_verifier"] and body["redirect_uri"].endswith(
                    "/api/integrations/github/callback"
                )
            return httpx.Response(
                200,
                json={
                    "access_token": "ghu_access-secret",
                    "refresh_token": "ghr_refresh-secret",
                    "expires_in": 28800,
                },
            )
        assert (
            request.url.host == "api.github.com"
            and request.headers["authorization"] == "Bearer ghu_access-secret"
        )
        path = request.url.path
        if path == "/user":
            data = {"id": 101, "login": "developer"}
        elif path == "/user/installations":
            data = {"installations": [{"id": 55, "account": {"login": "developer"}}]}
        elif path == "/user/installations/55/repositories":
            data = {
                "total_count": 1,
                "repositories": [
                    {
                        "id": 808,
                        "name": "private-demo",
                        "full_name": "developer/private-demo",
                        "private": True,
                        "default_branch": "main",
                        "html_url": "https://github.com/developer/private-demo",
                    }
                ],
            }
        elif path == "/repositories/808":
            data = {"id": 808}
        else:
            raise AssertionError("Unexpected GitHub path")
        return httpx.Response(200, json=data)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        gh,
        "httpx",
        SimpleNamespace(
            Client=lambda **kw: httpx.Client(transport=transport, **kw), HTTPError=httpx.HTTPError
        ),
    )
    return state


def link(client):
    result = client.post("/api/integrations/github/authorize")
    assert result.status_code == 200
    params = parse_qs(urlsplit(result.json()["url"]).query)
    assert params["code_challenge_method"] == ["S256"] and params["scope"] == ["offline_access"]
    callback = client.get(
        "/api/integrations/github/callback",
        params={"state": params["state"][0], "code": "test-authorization-code"},
        follow_redirects=False,
    )
    assert callback.status_code == 303
    return params["state"][0]


def test_github_pkce_selected_private_repository_and_encrypted_credentials(client, db, github):
    user = register(client)
    state = link(client)
    row = db.get(GitHubConnection, user["id"])
    assert row.access_token != "ghu_access-secret" and row.refresh_token != "ghr_refresh-secret"
    assert gh.unseal(row.access_token) == "ghu_access-secret"
    status = client.get("/api/integrations/github")
    assert status.json()["login"] == "developer" and "secret" not in status.text
    assert client.get("/api/integrations/github/installations/55/repositories").json()[
        "repositories"
    ][0]["private"]
    connected = client.post(
        "/api/integrations/github/repositories", json={"installation_id": 55, "repository_id": 808}
    )
    assert connected.status_code == 201
    repo = db.get(Repository, connected.json()["repository"]["id"])
    assert repo.github_repository_id == "808" and repo.github_connection_user_id == user["id"]
    assert (
        client.get(
            "/api/integrations/github/callback", params={"state": state, "code": "repeat"}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/integrations/github/repositories",
            json={"installation_id": 999, "repository_id": 808},
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/integrations/github/repositories",
            json={"installation_id": 55, "repository_id": 999},
        ).status_code
        == 404
    )


def test_github_state_csrf_and_cross_user_access_are_restricted(client, db, github):
    register(client)
    assert (
        client.post(
            "/api/integrations/github/authorize", headers={"X-CSRF-Token": "wrong"}
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/integrations/github/callback", params={"state": "attacker", "code": "code"}
        ).status_code
        == 400
    )
    link(client)
    register(client, "another@example.com")
    assert client.get("/api/integrations/github").json()["connected"] is False
    assert client.get("/api/integrations/github/installations").status_code == 403
    assert (
        client.post(
            "/api/integrations/github/repositories",
            json={"installation_id": 55, "repository_id": 808},
        ).status_code
        == 403
    )


def test_refresh_rotation_and_disconnect_fail_closed(client, db, github):
    user = register(client)
    link(client)
    row = db.get(GitHubConnection, user["id"])
    row.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert gh.token_for(user["id"]) == "ghu_access-secret" and github["refreshes"] == 1
    github["error"] = True
    result = client.get("/api/integrations/github/installations")
    assert result.status_code == 403 and "provider-secret" not in result.text
    assert client.delete("/api/integrations/github").status_code == 200
    db.expire_all()
    assert db.scalar(select(GitHubConnection)) is None


def test_git_fetch_credentials_stay_out_of_arguments_and_config(tmp_path, monkeypatch):
    from api.ingestion import sources

    sources.git(tmp_path, "init", "--bare")
    original = sources.subprocess.Popen
    captured = []

    def popen(args, **kw):
        captured.append((args, kw["env"]))
        return original(args, **kw)

    monkeypatch.setattr(sources.subprocess, "Popen", popen)
    assert (
        sources.git(tmp_path, "rev-parse", "--is-bare-repository", auth_token="test-private-token")
        == "true"
    )
    args, env = captured[0]
    assert "test-private-token" not in " ".join(args)
    assert env["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraHeader"
    assert "extraheader" not in (tmp_path / "config").read_text().lower()
