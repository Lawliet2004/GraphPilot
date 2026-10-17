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


def test_codespace_url_and_http_restrictions():
    assert (
        public_url(18080, environ={"CODESPACE_NAME": "my-demo"})
        == "https://my-demo-18080.app.github.dev"
    )
    assert public_url(18080, environ={}) == "http://127.0.0.1:18080"
    for url in [
        "http://public.example",
        "https://user:secret@example.com",
        "https://example.com/path",
        "https://example.com?secret=yes",
        "https://example.com\nGP_COOKIE_SECURE=false",
    ]:
        with pytest.raises(ValueError):
            public_url(18080, url)
