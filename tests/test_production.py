"""Production profile behavior over HTTPS without claiming a deployed TLS gateway."""

import json
import os
import subprocess
import sys

import pytest
from pydantic import ValidationError

from api.config import Settings


def test_production_rejects_insecure_cookie_and_origin_settings():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            environment="production",
            cookie_secure=False,
            origins=["https://app.example"],
        )
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            environment="production",
            cookie_secure=True,
            origins=["http://app.example"],
        )


def test_production_profile_secure_cookies_headers_and_restricted_origin():
    env = {
        **os.environ,
        "GP_ENVIRONMENT": "production",
        "GP_COOKIE_SECURE": "true",
        "GP_ORIGINS": '["https://app.example"]',
        "GP_PUBLIC_URL": "https://app.example",
        "GP_LLM_BASE_URL": "",
        "GP_LLM_MODEL": "",
    }
    script = """
import json
from fastapi.testclient import TestClient
from api.main import app
assert app.docs_url is None
assert app.redoc_url is None
assert app.openapi_url is None
with TestClient(app, base_url="https://app.example", headers={"Origin":"https://app.example"}) as client:
 for path in ("/api/docs", "/api/redoc", "/api/openapi.json", "/redoc", "/openapi.json"):
  assert client.get(path).status_code == 404
 response=client.post("/api/auth/register", json={"name":"Production profile fixture", "email":"production-fixture@example.com", "password":"test-production-long-password"})
 assert response.status_code == 201
 cookies=response.headers.get_list("set-cookie")
 session=next(c for c in cookies if c.startswith("gp_session="))
 assert "Secure" in session and "HttpOnly" in session and "SameSite=lax" in session
 assert response.headers["strict-transport-security"] == "max-age=31536000"
 assert response.headers["x-frame-options"] == "DENY"
 assert response.headers["cache-control"] == "no-store"
 assert client.get("/api/auth/session").status_code == 200
 assert client.get("http://app.example/api/auth/session").status_code == 401
 client.headers["X-CSRF-Token"]=response.json()["csrf"]
 assert client.post("/api/auth/logout", headers={"Origin":"https://evil.example"}).status_code == 403
 denied=client.options("/api/auth/session", headers={"Origin":"https://evil.example", "Access-Control-Request-Method":"GET"})
 assert "access-control-allow-origin" not in denied.headers
 assert client.post("/api/auth/logout").status_code == 200
 print(json.dumps({"production_profile":True, "secure_cookies":True, "headers":True, "origin_restrictions":True, "http_cookie_withheld":True}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert json.loads(completed.stdout)["secure_cookies"]


@pytest.mark.parametrize("url", ["http://app.example", "https://other.example"])
def test_production_requires_allowed_https_public_url(url):
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            environment="production",
            cookie_secure=True,
            origins=["https://app.example"],
            public_url=url,
        )


@pytest.mark.parametrize(
    "url",
    [
        "https://",
        "https://app.example/path",
        "https://user@app.example",
        "https://app.example?token=secret",
        "https://app.example#fragment",
        "https://app.example:99999",
        "https://app.example ",
    ],
)
def test_origins_and_public_url_reject_malformed_values(url):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, origins=[url])
    with pytest.raises(ValidationError):
        Settings(_env_file=None, public_url=url)


def test_production_accepts_matching_public_url_and_normalizes_trailing_slash():
    cfg = Settings(
        _env_file=None,
        environment="production",
        cookie_secure=True,
        origins=["https://app.example"],
        public_url="https://app.example/",
    )
    assert cfg.public_url == "https://app.example"


def test_configuration_errors_and_representation_omit_credentials():
    credentials = {
        "database_url": "postgresql+psycopg://fixture:private-database-value@localhost/fixture",
        "falkor_password": "private-graph-value",
        "llm_api_key": "private-provider-value",
        "github_token": "private-github-value",
        "smtp_username": "private-mail-user",
        "smtp_password": "private-mail-value",
    }
    cfg = Settings(_env_file=None, **credentials)
    assert all(value not in repr(cfg) for value in credentials.values())
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, environment="production", cookie_secure=False, **credentials)
    assert "Production requires" in str(error.value)
    assert all(value not in str(error.value) for value in credentials.values())
