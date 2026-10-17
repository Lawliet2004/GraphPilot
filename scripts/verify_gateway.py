"""Run the production API and Nginx/TLS against disposable native data.

Needs an Nginx executable, OpenSSL, a built frontend and reachable configured
PostgreSQL/FalkorDB. Never stops development services or changes their settings.
"""

import argparse
import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx
from falkordb import FalkorDB
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from api.config import settings
from scripts.smoke_gateway import exercise, expect
from scripts.verification_tls import certificate


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def stop(process):
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def wait_ready(client, process):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Owned verification process exited before readiness")
        try:
            if client.get("/api/health/ready", timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise RuntimeError("Owned verification gateway did not become ready")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--nginx",
        type=Path,
        default=Path(shutil.which("nginx") or ".tools/nginx-download/extracted/usr/sbin/nginx"),
    )
    args = parser.parse_args()
    if not __debug__:
        parser.error("Verification requires assertions; run Python without -O")
    nginx = args.nginx.resolve()
    if not nginx.is_file() or not Path("app/dist/index.html").is_file():
        parser.error("Supply an Nginx binary and run npm --prefix app run build first")
    cfg = settings()
    database = "graphpilot_gateway_" + uuid.uuid4().hex[:12]
    base = make_url(cfg.database_url)
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    isolated = create_engine(base.set(database=database))
    created, api, worker, gateway = False, None, None, None
    root_parent = Path(".data/gateway").resolve()
    root_parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "scope": "Native Nginx + real production-profile API/worker + PostgreSQL/FalkorDB, ephemeral locally trusted TLS. No container or public certificate claim.",
        "nginx_version": subprocess.run(
            [str(nginx), "-v"], capture_output=True, text=True, check=True
        ).stderr.strip(),
        "status": "failed",
    }
    with tempfile.TemporaryDirectory(prefix="probe-", dir=root_parent) as temporary:
        root = Path(temporary)
        os.chmod(root, 0o700)
        with (root / "process.log").open("w") as logs:
            os.chmod(root / "process.log", 0o600)
            try:
                api_port, tls_port = free_port(), free_port()
                origin = f"https://127.0.0.1:{tls_port}"
                cert, key = certificate(root / "tls")
                context = ssl.create_default_context(cafile=str(cert))
                env = {
                    **os.environ,
                    "GP_DATABASE_URL": base.set(database=database).render_as_string(
                        hide_password=False
                    ),
                    "GP_DATA_DIR": str(root / "artifacts"),
                    "GP_ENVIRONMENT": "production",
                    "GP_COOKIE_SECURE": "true",
                    "GP_ORIGINS": json.dumps([origin]),
                    "GP_PUBLIC_URL": origin,
                    "GP_ALLOWED_LOCAL_ROOTS": "[]",
                    "GP_LLM_BASE_URL": "",
                    "GP_LLM_MODEL": "",
                    "GP_LLM_API_KEY": "",
                    "GP_GITHUB_TOKEN": "",
                    "GP_SMTP_HOST": "",
                    "GP_SMTP_FROM": "",
                    "GP_FALKOR_HOST": cfg.falkor_host,
                    "GP_FALKOR_PORT": str(cfg.falkor_port),
                }
                with admin.connect() as connection:
                    connection.execute(text(f'CREATE DATABASE "{database}"'))
                    created = True
                subprocess.run(
                    [sys.executable, "-m", "alembic", "upgrade", "head"],
                    env=env,
                    check=True,
                    stdout=logs,
                    stderr=logs,
                    timeout=30,
                )

                def start_api():
                    return subprocess.Popen(
                        [
                            sys.executable,
                            "-m",
                            "uvicorn",
                            "api.main:app",
                            "--host",
                            "127.0.0.1",
                            "--port",
                            str(api_port),
                            "--no-access-log",
                        ],
                        env=env,
                        stdout=logs,
                        stderr=logs,
                    )

                api = start_api()
                worker = subprocess.Popen(
                    [sys.executable, "-m", "api.worker"], env=env, stdout=logs, stderr=logs
                )
                gateway_config = (
                    Path("app/nginx.conf")
                    .read_text()
                    .replace(
                        "listen 80;",
                        f"listen 127.0.0.1:{tls_port} ssl;\n"
                        f"  ssl_certificate {cert};\n  ssl_certificate_key {key};\n"
                        "  ssl_protocols TLSv1.2 TLSv1.3;",
                    )
                    .replace("/usr/share/nginx/html", str(Path("app/dist").resolve()))
                    .replace("http://api:8000", f"http://127.0.0.1:{api_port}")
                )
                for name in ("body", "proxy", "fastcgi", "uwsgi", "scgi"):
                    (root / name).mkdir()
                config = root / "nginx.conf"
                config.write_text(
                    f"pid {root}/nginx.pid;\nerror_log stderr;\n"
                    "events {}\nhttp {\naccess_log off;\n"
                    "types { text/html html; text/css css; application/javascript js; font/woff2 woff2; }\n"
                    f"client_body_temp_path {root}/body;\nproxy_temp_path {root}/proxy;\n"
                    f"fastcgi_temp_path {root}/fastcgi;\nuwsgi_temp_path {root}/uwsgi;\n"
                    f"scgi_temp_path {root}/scgi;\n" + gateway_config + "\n}\n"
                )
                subprocess.run(
                    [str(nginx), "-t", "-p", str(root), "-c", str(config)],
                    check=True,
                    stdout=logs,
                    stderr=logs,
                    timeout=10,
                )
                gateway = subprocess.Popen(
                    [str(nginx), "-p", str(root), "-c", str(config), "-g", "daemon off;"],
                    stdout=logs,
                    stderr=logs,
                )
                with httpx.Client(
                    base_url=origin,
                    verify=context,
                    trust_env=False,
                    headers={"Origin": origin},
                    timeout=45,
                ) as client:
                    wait_ready(client, gateway)

                    def restart(client):
                        nonlocal api
                        stop(api)
                        expect(client.get("/api/health/ready"), 502)
                        api = start_api()
                        wait_ready(client, api)
                        # Check while the valid owner session is still present.
                        assert client.cookies.get("gp_session")
                        expect(client.get(f"http://127.0.0.1:{api_port}/api/auth/session"), 401)
                        report["secure_cookie_withheld_over_http"] = True

                    exercise(client, report, restart)
                    try:
                        httpx.get(origin, timeout=5, trust_env=False)
                    except httpx.ConnectError as exc:
                        assert "CERTIFICATE_VERIFY_FAILED" in str(exc)
                        report["untrusted_tls_rejected"] = True
                    else:
                        raise AssertionError(
                            "Ephemeral certificate was unexpectedly publicly trusted"
                        )
                for _ in range(100):
                    with isolated.connect() as connection:
                        remaining = connection.scalar(text("SELECT count(*) FROM repositories"))
                    if remaining == 0:
                        break
                    time.sleep(0.1)
                assert remaining == 0, "Owned removal did not finish"
                report.update(
                    owned_repository_removed=True, tls_certificate_verified=True, status="passed"
                )
            finally:
                for process in (gateway, worker, api):
                    stop(process)
                if created:
                    # Only names belonging to rows in our unique disposable database.
                    with isolated.connect() as connection:
                        exists = connection.scalar(text("SELECT to_regclass('repositories')"))
                        ids = (
                            connection.scalars(text("SELECT id FROM repositories")).all()
                            if exists
                            else []
                        )
                    graph = FalkorDB(
                        host=cfg.falkor_host,
                        port=cfg.falkor_port,
                        password=cfg.falkor_password,
                        unix_socket_path=cfg.falkor_socket,
                    )
                    for name in graph.list_graphs() if ids else []:
                        if any(name.startswith("gp_" + i.replace("-", "") + "_") for i in ids):
                            graph.select_graph(name).delete()
                    isolated.dispose()
                    with admin.connect() as connection:
                        connection.execute(text(f'DROP DATABASE "{database}" WITH (FORCE)'))
                    report["disposable_database_removed"] = True
                admin.dispose()
                Path("docs/GATEWAY_VERIFICATION.json").write_text(
                    json.dumps(report, indent=2) + "\n"
                )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
