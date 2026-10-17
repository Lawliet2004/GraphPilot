#!/usr/bin/env python3
"""Read-only deployment checks; never creates accounts, indexes data or sends email."""

import argparse
import json
import re
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def check(url):
    parsed = urlparse(url)
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or parsed.scheme == "http"
        and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
    ):
        raise ValueError("Supply an HTTPS origin, or a loopback HTTP origin")
    url = url.rstrip("/")
    opener = build_opener(NoRedirect)
    observations = []

    def request(path, expected, body=None):
        req = Request(
            url + path,
            data=body,
            headers={
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
        )
        started = time.perf_counter()
        try:
            response = opener.open(req, timeout=45)
        except HTTPError as exc:
            response = exc
        with response:
            content = response.read(262144)
            assert response.status in expected, (
                f"Unexpected HTTP status for {path}: {response.status}"
            )
            assert response.headers.get("X-Content-Type-Options") == "nosniff", (
                f"Missing security header: {path}"
            )
            if parsed.scheme == "https":
                assert response.headers.get("Strict-Transport-Security"), f"Missing HSTS: {path}"
            observations.append(
                {
                    "path": path,
                    "status": response.status,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                }
            )
            return content, response.headers

    html, headers = request("/", {200})
    assert b'id="root"' in html, "Frontend application root missing"
    assert headers.get("Content-Security-Policy"), "Frontend CSP missing"
    assets = re.findall(rb'<script[^>]+src="([^\"]+)"', html)
    assert assets, "Frontend JavaScript entry missing"
    # Keep checks within the selected origin; never follow provider-controlled URLs.
    entry = assets[0].decode()
    assert entry.startswith("/") and not entry.startswith("//"), "Unexpected frontend asset origin"
    request(entry, {200})
    health, _ = request("/api/health/ready", {200})
    assert json.loads(health).get("status") == "ready", "Database readiness failed"
    request("/api/auth/session", {401})
    request("/api/admin/users", {401})
    request("/api/repositories/00000000-0000-0000-0000-000000000000/graph", {401})
    request("/api/mcp/", {401, 404}, b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}')
    return {
        "status": "passed",
        "scope": "Read-only public deployment checks; not a full user journey",
        "checks": observations,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not __debug__:
        parser.error("Checks require assertions; run Python without -O")
    try:
        result = check(args.url)
    except Exception as exc:
        # Exception strings can include a URL or private response content.
        result = {
            "status": "failed",
            "error_type": type(exc).__name__,
            "notice": "A deployment check failed. Inspect the deployment privately.",
        }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
