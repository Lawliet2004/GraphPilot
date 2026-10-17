import io
import json
from unittest.mock import Mock

import pytest

from scripts import uptime_check


def response(body):
    result = io.BytesIO(body)
    result.status = 200
    result.headers = {
        "X-Content-Type-Options": "nosniff",
        "Strict-Transport-Security": "max-age=31536000",
        "Content-Security-Policy": "default-src 'self'",
    }
    return result


def test_sleeping_backend_is_never_probed(monkeypatch):
    opener = Mock()
    opener.open.return_value = response(b'<div id="root"></div>')
    monkeypatch.setattr(uptime_check, "build_opener", lambda *args: opener)
    result = uptime_check.check("https://gp-code.vercel.app")
    assert result["status"] == "passed" and result["backend_checked"] is False
    assert opener.open.call_count == 1
    assert opener.open.call_args.args[0].full_url == "https://gp-code.vercel.app/"


def test_always_awake_backend_readiness_is_required(monkeypatch):
    opener = Mock()
    opener.open.side_effect = [
        response(b'<div id="root"></div>'),
        response(json.dumps({"status": "unavailable"}).encode()),
    ]
    monkeypatch.setattr(uptime_check, "build_opener", lambda *args: opener)
    result = uptime_check.check("https://gp-code.vercel.app", "always-awake")
    assert result["status"] == "failed" and result["backend_checked"] is True
    assert opener.open.call_count == 2


@pytest.mark.parametrize(
    "url",
    [
        "https://example-18080.app.github.dev",
        "http://gp-code.vercel.app",
        "https://secret@example.com",
        "https://example.com/?key=private",
    ],
)
def test_monitor_rejects_unstable_or_sensitive_target(url):
    with pytest.raises(ValueError):
        uptime_check.check(url)
