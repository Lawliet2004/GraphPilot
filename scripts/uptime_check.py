#!/usr/bin/env python3
"""Bounded external availability probe; Codespaces mode checks static Vercel only."""

import argparse
import json
import time
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, build_opener

from scripts.demo_check import NoRedirect


def check(url, backend_kind="codespaces"):
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or parsed.hostname.endswith(".app.github.dev")
    ):
        raise ValueError("Use a stable HTTPS frontend origin, never a Codespace forwarding URL")
    if backend_kind not in {"codespaces", "always-awake"}:
        raise ValueError("Unknown backend kind")
    paths = ["/"]
    if backend_kind == "always-awake":
        paths.append("/api/health/ready")
    observations = []
    opener = build_opener(NoRedirect)
    for path in paths:
        started = time.monotonic()
        try:
            response = opener.open(
                Request(url.rstrip("/") + path, headers={"User-Agent": "GraphPilot-availability"}),
                timeout=20,
            )
        except HTTPError as exc:
            response = exc
        with response:
            content = response.read(262144)
            valid = (
                response.status == 200
                and response.headers.get("X-Content-Type-Options") == "nosniff"
                and bool(response.headers.get("Strict-Transport-Security"))
            )
            if path == "/":
                valid = valid and b'id="root"' in content and bool(
                    response.headers.get("Content-Security-Policy")
                )
            else:
                try:
                    health = json.loads(content)
                    valid = valid and health.get("status") == "ready"
                except (ValueError, AttributeError):
                    valid = False
            observations.append(
                {
                    "path": path,
                    "http_status": response.status,
                    "passed": bool(valid),
                    "duration_ms": round((time.monotonic() - started) * 1000),
                }
            )
    return {
        "status": "passed" if all(r["passed"] for r in observations) else "failed",
        "scope": "frontend and backend" if backend_kind == "always-awake" else "static frontend only",
        "backend_checked": backend_kind == "always-awake",
        "observations": observations,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--backend-kind", choices=["codespaces", "always-awake"], default="codespaces")
    args = parser.parse_args()
    try:
        result = check(args.url, args.backend_kind)
    except Exception as exc:
        # Keep provider response bodies, URLs and exception details out of public CI.
        result = {"status": "failed", "error_type": type(exc).__name__}
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
