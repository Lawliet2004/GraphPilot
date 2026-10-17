import json
import stat

import pytest

from scripts.cloud_demo import prepare, public_url


def test_cloud_demo_isolated_configuration_preserves_secrets_and_https(tmp_path):
    state = tmp_path / "demo"
    path = prepare(state, "https://demo-18080.app.github.dev", 18080)
    values = dict(line.split("=", 1) for line in path.read_text().splitlines())
    assert values["GP_ENVIRONMENT"] == "production"
    assert values["GP_COOKIE_SECURE"] == "true"
    assert values["GP_MCP_ENABLED"] == "true"
    assert values["GP_LLM_MODEL"] == ""  # No billable model is silently configured.
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(state.stat().st_mode) == 0o700
    assert len(values["POSTGRES_PASSWORD"]) >= 64
    prepare(state, "https://resumed-18080.app.github.dev", 18080)
    updated = dict(line.split("=", 1) for line in path.read_text().splitlines())
    assert values["POSTGRES_PASSWORD"] == updated["POSTGRES_PASSWORD"]
    assert json.loads(updated["GP_ORIGINS"]) == ["https://resumed-18080.app.github.dev"]
    assert "X-Forwarded-Proto https" in (state / "nginx.conf").read_text()
    assert "Strict-Transport-Security" in (state / "nginx.conf").read_text()
    gateway = (state / "nginx.conf").read_text()
    assert "default $http_origin;" in gateway
    assert (
        '"resumed-18080.app.github.dev|http://localhost:18080|same-origin" '
        '"https://resumed-18080.app.github.dev";' in gateway
    )
    assert "proxy_set_header Host resumed-18080.app.github.dev;" in gateway


def test_other_gateways_do_not_rewrite_origins(tmp_path):
    state = tmp_path / "demo"
    prepare(state, "https://demo.example.com", 18081)
    gateway = (state / "nginx.conf").read_text()
    assert "$graphpilot_origin" not in gateway
    assert "proxy_set_header Host $http_host;" in gateway


def test_vercel_origin_keeps_old_codespace_login_and_foreign_origin_rejection(tmp_path):
    state = tmp_path / "demo"
    old = "https://demo-18080.app.github.dev"
    path = prepare(state, "https://gp-demo.vercel.app", 18080, [old, old])
    values = dict(line.split("=", 1) for line in path.read_text().splitlines())
    assert values["GP_PUBLIC_URL"] == "https://gp-demo.vercel.app"
    assert json.loads(values["GP_ORIGINS"]) == ["https://gp-demo.vercel.app", old]
    gateway = (state / "nginx.conf").read_text()
    assert '"demo-18080.app.github.dev|http://localhost:18080|same-origin"' in gateway
    assert '"https://demo-18080.app.github.dev";' in gateway
    assert "default $http_origin;" in gateway
    assert "return 308 https://gp-demo.vercel.app$request_uri;" in gateway
    prepare(state, "https://gp-demo.vercel.app", 18080)
    resumed = dict(line.split("=", 1) for line in path.read_text().splitlines())
    assert json.loads(resumed["GP_ORIGINS"]) == ["https://gp-demo.vercel.app", old]
    with pytest.raises(ValueError):
        prepare(state, "https://gp-demo.vercel.app", 18080, ["https://evil.example/path"])
    with pytest.raises(ValueError):
        prepare(state, "https://gp-demo.vercel.app", 18080, ["http://localhost:5173"])


def test_codespace_url_and_http_restrictions():
    assert (
        public_url(18080, environ={"CODESPACE_NAME": "my-demo"})
        == "https://my-demo-18080.app.github.dev"
    )
    assert public_url(18080, environ={}) == "http://127.0.0.1:18080"
    previous = "https://original-18080.app.github.dev"
    assert public_url(18080, environ={}, previous=previous) == previous
    assert public_url(18080, "https://explicit.example", environ={}, previous=previous) == (
        "https://explicit.example"
    )
    assert public_url(18080, environ={"CODESPACE_NAME": "resumed"}, previous=previous) == (
        "https://resumed-18080.app.github.dev"
    )
    assert (
        public_url(
            18080, environ={"CODESPACE_NAME": "resumed"}, previous="https://gp-demo.vercel.app"
        )
        == "https://gp-demo.vercel.app"
    )
    for url in [
        "http://public.example",
        "https://user:secret@example.com",
        "https://example.com/path",
        "https://example.com?secret=yes",
        "https://example.com\nGP_COOKIE_SECURE=false",
    ]:
        with pytest.raises(ValueError):
            public_url(18080, url)
