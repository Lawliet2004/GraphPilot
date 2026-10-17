#!/usr/bin/env python3
"""Start an isolated full-stack demo in Codespaces or on a Docker host.

Uses only Python's standard library; no cloud secrets or payment method needed.
Never edits the developer .env or deletes volumes. Port visibility stays private
until the owner chooses Public in GitHub's Ports panel.
"""

import argparse
import json
import os
import re
import secrets
import shlex
import subprocess
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


def public_url(port, explicit=None, environ=None):
    env = os.environ if environ is None else environ
    if explicit:
        url = explicit.rstrip("/")
    elif env.get("CODESPACE_NAME"):
        name = env["CODESPACE_NAME"]
        domain = env.get("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN", "app.github.dev")
        if not re.fullmatch(r"[a-z0-9-]+", name) or not re.fullmatch(r"[a-z0-9.-]+", domain):
            raise ValueError("Invalid Codespaces hostname")
        url = f"https://{name}-{port}.{domain}"
    else:
        url = f"http://127.0.0.1:{port}"
    parsed = urlparse(url)
    if (
        not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.params
        or parsed.query
        or parsed.fragment
        or parsed.scheme not in {"http", "https"}
        or re.search(r"[\s$#'\"\\]", url)
    ):
        raise ValueError("Supply an HTTP(S) origin without a path, credentials or whitespace")
    # Plain HTTP is allowed only for loopback verification, never a public demo.
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Public demos require HTTPS")
    return url


def save_private(path, content):
    if path.is_symlink():
        raise ValueError("Refusing to overwrite a symlink")
    temporary = path.with_name(path.name + "." + secrets.token_hex(8) + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def prepare(state, address, port):
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    state.chmod(0o700)
    env_file = state / "compose.env"
    values = (
        dict(
            line.split("=", 1)
            for line in env_file.read_text().splitlines()
            if "=" in line and not line.startswith("#")
        )
        if env_file.exists()
        else {}
    )
    password = values.get("POSTGRES_PASSWORD") or secrets.token_hex(32)
    secure = address.startswith("https://")
    dsn = f"postgresql+psycopg://graphpilot:{password}@postgres:5432/graphpilot"
    values.update(
        {
            "POSTGRES_USER": "graphpilot",
            "POSTGRES_DB": "graphpilot",
            "POSTGRES_PASSWORD": password,
            "GP_DATABASE_URL": dsn,
            "GP_COMPOSE_DATABASE_URL": dsn,
            "GP_WEB_PORT": str(port),
            "GP_ENVIRONMENT": "production" if secure else "development",
            "GP_COOKIE_SECURE": str(secure).lower(),
            "GP_PUBLIC_URL": address,
            "GP_ORIGINS": json.dumps([address]),
            "GP_ALLOWED_LOCAL_ROOTS": "[]",
            "GP_MCP_ENABLED": "true",
            "GP_LLM_BASE_URL": "",
            "GP_LLM_MODEL": "",
            "GP_LLM_API_KEY": "",
        }
    )
    save_private(env_file, "\n".join(f"{k}={v}" for k, v in values.items()) + "\n")
    gateway = (ROOT / "app/nginx.conf").read_text()
    if secure:
        gateway = gateway.replace(
            "proxy_set_header X-Forwarded-Proto $scheme;",
            "proxy_set_header X-Forwarded-Proto https;",
        )
        gateway = gateway.replace(
            "  server_name _;",
            '  server_name _;\n  add_header Strict-Transport-Security "max-age=31536000" always;',
        )
    save_private(state / "nginx.conf", gateway)
    save_private(
        state / "override.json",
        json.dumps(
            {
                "services": {
                    "web": {
                        "volumes": [f"{state / 'nginx.conf'}:/etc/nginx/conf.d/default.conf:ro"],
                    }
                }
            }
        ),
    )
    return env_file


def docker_command():
    command = ["docker"]
    probe = subprocess.run(
        command + ["info", "--format", "{{.ServerVersion}}"], capture_output=True, text=True
    )
    if probe.returncode:
        # Existing host terminals may predate membership in the docker group.
        fallback = ["sg", "docker", "-c", "docker info --format '{{.ServerVersion}}'"]
        if subprocess.run(fallback, capture_output=True).returncode:
            raise RuntimeError("Docker is unavailable. Start Docker or rebuild the Codespace.")
        return lambda args: ["sg", "docker", "-c", shlex.join(["docker", *args])]
    return lambda args: ["docker", *args]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=["start", "stop", "status", "check", "admin", "mcp-token", "mcp-revoke"]
    )
    parser.add_argument("--port", type=int, default=18080)
    parser.add_argument("--public-url")
    parser.add_argument("--project", default="graphpilot-cloud-demo")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--email", help="Existing account email for admin/token commands")
    parser.add_argument("--days", type=int, default=7, choices=range(1, 31), metavar="1..30")
    parser.add_argument("--token-id", help="Non-secret token ID for mcp-revoke")
    args = parser.parse_args()
    if (
        not re.fullmatch(r"graphpilot-cloud-[a-z0-9-]+", args.project)
        or not 1024 <= args.port <= 65535
    ):
        parser.error("Use a graphpilot-cloud-* project and an unprivileged valid port")
    state = ROOT / ".data/cloud-demo" / args.project
    env_file = state / "compose.env"
    address = None
    if args.action == "start":
        address = public_url(args.port, args.public_url)
        env_file = prepare(state, address, args.port)
    elif not env_file.exists():
        parser.error("This demo has not been started")
    docker = docker_command()
    base = [
        "compose",
        "--env-file",
        str(env_file),
        "-p",
        args.project,
        "-f",
        str(ROOT / "docker-compose.yml"),
        "-f",
        str(state / "override.json"),
    ]
    env = {**os.environ, "GP_ENV_FILE": str(env_file)}
    # Do not inherit a different local deployment's Compose interpolation values.
    for key in ("GP_WEB_PORT", "POSTGRES_PASSWORD", "GP_COMPOSE_DATABASE_URL"):
        env.pop(key, None)
    if args.action in {"admin", "mcp-token", "mcp-revoke"}:
        cli = ["exec", "api", "python", "-m", "api.cli"]
        if args.action == "admin":
            if not args.email:
                parser.error("Supply --email for your administrator")
            subprocess.run(
                docker(base + cli + ["create-admin", args.email]), cwd=ROOT, env=env, check=True
            )
        elif args.action == "mcp-revoke":
            if not args.token_id or not re.fullmatch(r"[a-f0-9]{64}", args.token_id):
                parser.error("Supply a valid --token-id")
            subprocess.run(
                docker(base + cli + ["revoke-mcp-token", args.token_id]),
                cwd=ROOT,
                env=env,
                check=True,
            )
        else:
            if not args.email:
                parser.error("Supply --email for an existing active account")
            identifier = secrets.token_hex(12)
            remote_path = f"/data/mcp-{identifier}.token"
            target = state / f"mcp-{identifier}.token"
            command = base + [
                "exec",
                "-T",
                "api",
                "python",
                "-m",
                "api.cli",
                "create-mcp-token",
                args.email,
                "--days",
                str(args.days),
                "--output",
                remote_path,
            ]
            subprocess.run(docker(command), cwd=ROOT, env=env, check=True)
            try:
                result = subprocess.run(
                    docker(base + ["exec", "-T", "api", "cat", remote_path]),
                    cwd=ROOT,
                    env=env,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                save_private(target, result.stdout)
            finally:
                subprocess.run(
                    docker(base + ["exec", "-T", "api", "rm", "-f", remote_path]),
                    cwd=ROOT,
                    env=env,
                    check=True,
                )
            print("Owner-only MCP token file:", target)
        return
    if args.action == "check":
        from urllib.request import urlopen

        values = dict(
            line.split("=", 1) for line in env_file.read_text().splitlines() if "=" in line
        )
        port = values["GP_WEB_PORT"]
        with urlopen(f"http://127.0.0.1:{port}/api/health/ready", timeout=15) as response:
            health = json.load(response)
        if health.get("status") != "ready":
            raise RuntimeError("Demo is not ready")
        print("PostgreSQL and FalkorDB ready. Public browser checks are separate.")
        return
    command = {
        "start": ["up", "-d", "--wait", "--wait-timeout", "240"],
        "stop": ["stop"],
        "status": ["ps"],
    }[args.action]
    if args.action == "start" and args.build:
        command.append("--build")
    subprocess.run(docker(base + command), cwd=ROOT, env=env, check=True)
    if args.action == "start":
        print(f"GraphPilot: {address}")
        print("MCP endpoint: " + address + "/api/mcp/ (requires a per-user token)")
        print(
            f"Codespaces: open Ports → {args.port} → Port Visibility → Public when ready to share."
        )
        print("Create your account in the app. No default administrator or password is shipped.")
    elif args.action == "stop":
        print("Demo stopped. Database and source volumes preserved.")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(
            f"Cloud demo failed ({type(exc).__name__}); no volumes were deleted."
        ) from None
