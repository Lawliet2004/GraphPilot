"""Application smoke checks against an explicitly selected disposable deployment.

Creates labeled test accounts and an uploaded source fixture. The owning harness
must destroy its isolated database after the probe (accounts/audits are retained).
"""

import argparse
import io
import json
import re
import secrets
import time
import uuid
import zipfile
from pathlib import Path

import httpx


def expect(response, status):
    assert response.status_code == status, f"Expected HTTP {status}, got {response.status_code}"
    return response


def register(client):
    response = expect(
        client.post(
            "/api/auth/register",
            json={
                "name": "Disposable gateway verification",
                "email": f"gateway-{uuid.uuid4()}@graphpilot.invalid",
                "password": secrets.token_urlsafe(24),
            },
        ),
        201,
    )
    client.headers["X-CSRF-Token"] = response.json()["csrf"]
    return response


def exercise(client, report, restart=None):
    if not __debug__:
        raise RuntimeError("Verification requires assertions; run Python without -O")
    page = expect(client.get("/workspace"), 200)
    assert "<html" in page.text and "<script" in page.text
    assert "default-src 'self'" in page.headers["content-security-policy"]
    assert page.headers["x-content-type-options"] == "nosniff"
    assert page.headers["x-frame-options"] == "DENY"
    asset = re.search(r'<script[^>]+src="([^"]+)"', page.text)
    assert asset, "Built frontend entrypoint is missing"
    script = expect(client.get(asset[1]), 200)
    assert "javascript" in script.headers.get("content-type", "")
    expect(client.get("/api"), 404)
    expect(client.get("/api/health/ready"), 200)
    expect(client.get("/api/auth/session"), 401)
    response = register(client)
    session = next(
        c for c in response.headers.get_list("set-cookie") if c.startswith("gp_session=")
    )
    assert "HttpOnly" in session and "SameSite=lax" in session
    if str(client.base_url).startswith("https:"):
        assert "Secure" in session
        assert response.headers["strict-transport-security"] == "max-age=31536000"
    assert response.headers["cache-control"] == "no-store"
    expect(client.get("/api/auth/session"), 200)
    expect(client.post("/api/auth/logout", headers={"Origin": "https://denied.example"}), 403)
    expect(
        client.patch(
            "/api/auth/profile",
            headers={"X-CSRF-Token": "invalid"},
            json={"name": "Denied", "theme": "dark"},
        ),
        403,
    )
    denied = client.options(
        "/api/auth/session",
        headers={"Origin": "https://denied.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in denied.headers
    expect(client.post("/api/auth/login", content=b"x" * 65537), 413)
    large = expect(client.post("/api/repositories/upload", content=b"x" * (27 * 1024 * 1024)), 413)
    assert "nginx" in large.headers.get("server", "")
    report.update(
        spa_and_csp=True,
        cookies_and_headers=True,
        origin_csrf_cors=True,
        api_body_limit=True,
        gateway_upload_limit=True,
    )
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("gateway.py", "def gateway_probe():\n    return 'verified source'\n")
    repo = expect(
        client.post(
            "/api/repositories/upload",
            files={"file": ("gateway-verification.zip", archive.getvalue(), "application/zip")},
        ),
        201,
    ).json()["repository"]
    base = f"/api/repositories/{repo['id']}"
    for _ in range(300):
        job = expect(client.get(base + "/jobs"), 200).json()[0]
        if job["status"] in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.2)
    assert job["status"] == "succeeded", "Gateway fixture indexing did not succeed"
    node = expect(client.get(base + "/search?q=gateway_probe"), 200).json()["results"][0]
    evidence = base + "/evidence/" + node["id"]
    assert "return 'verified source'" in expect(client.get(evidence), 200).json()["content"]
    capabilities = expect(client.get("/api/capabilities"), 200).json()
    assert not capabilities["llm_configured"]
    # A separate browser session remains unauthorized for the owner's source.
    owner_cookies = httpx.Cookies(client.cookies)
    owner_csrf = client.headers["X-CSRF-Token"]
    client.cookies.clear()
    register(client)
    expect(client.get(evidence), 404)
    client.cookies.clear()
    client.cookies.update(owner_cookies)
    client.headers["X-CSRF-Token"] = owner_csrf
    if restart:
        restart(client)
        expect(client.get("/api/auth/session"), 200)
        assert "return 'verified source'" in expect(client.get(evidence), 200).json()["content"]
        report["api_restart_preserves_session_and_source"] = True
    expect(client.request("DELETE", base, json={"confirm_name": repo["name"]}), 202)
    for _ in range(300):
        if not any(
            r["id"] == repo["id"] for r in expect(client.get("/api/repositories"), 200).json()
        ):
            break
        time.sleep(0.2)
    expect(client.post("/api/auth/logout"), 200)
    expect(client.get("/api/auth/session"), 401)
    report.update(
        worker_indexing=True,
        exact_source_evidence=True,
        outsider_source_denied=True,
        graph_only=True,
        owner_removal_requested=True,
        logout_revoked=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument(
        "--disposable",
        action="store_true",
        required=True,
        help="Acknowledge this is an owned disposable deployment",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = {"scope": "Disposable HTTP gateway smoke; not a TLS/container certification"}
    with httpx.Client(
        base_url=args.url, headers={"Origin": args.url}, timeout=45, trust_env=False
    ) as client:
        exercise(client, report)
    report["status"] = "passed"
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
