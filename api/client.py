"""Remote GraphPilot CLI. No remote shell or repository-code execution."""

import argparse
import base64
import hashlib
import json
import os
import secrets
import stat
import sys
import time
import webbrowser
from pathlib import Path
from urllib.parse import urlsplit

import httpx


def challenge(value):
    return base64.urlsafe_b64encode(hashlib.sha256(value.encode()).digest()).decode().rstrip("=")


def origin(value):
    value = value.rstrip("/")
    p = urlsplit(value)
    if (
        p.username
        or p.password
        or not p.hostname
        or p.path
        or p.query
        or p.fragment
        or not (
            p.scheme == "https"
            or p.scheme == "http"
            and p.hostname in {"127.0.0.1", "localhost", "::1"}
        )
    ):
        raise ValueError("Use an HTTPS website origin, or HTTP on loopback for local testing")
    return value


def config_path():
    return (
        Path(os.getenv("XDG_CONFIG_HOME", str(Path.home() / ".config")))
        / "graphpilot"
        / "session.json"
    )


def save_session(path, data):
    if path.is_symlink():
        raise ValueError("Refusing a symlink for CLI credentials")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    temporary = path.with_name("session-" + secrets.token_hex(8) + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load_session(path):
    meta = path.lstat()
    if not stat.S_ISREG(meta.st_mode) or meta.st_mode & 0o077 or meta.st_size > 16384:
        raise ValueError("CLI credential file must be a private regular file (mode 600)")
    data = json.loads(path.read_text())
    origin(data["server"])
    if not isinstance(data.get("token"), str) or not data["token"].startswith("gp_mcp_"):
        raise ValueError("Run graphpilot login to create a CLI credential")
    return data


def call(client, method, path, **kwargs):
    response = client.request(method, path, **kwargs)
    if response.status_code >= 400:
        raise ValueError(
            f"Command failed (HTTP {response.status_code}). Check login, permissions and repository status."
        )
    return response.json()


def login(args, path):
    server = origin(args.server)
    verifier = secrets.token_urlsafe(48)
    with httpx.Client(
        base_url=server,
        headers={"Origin": server, "Sec-Fetch-Site": "same-origin"},
        timeout=45,
        follow_redirects=False,
        trust_env=False,
    ) as c:
        start = call(
            c,
            "POST",
            "/api/cli/device",
            json={"challenge": challenge(verifier), "write": args.write, "name": "GraphPilot CLI"},
        )
        expected = server + "/cli/authorize?code=" + start["user_code"].replace("-", "")
        if start["verification_uri"] != expected:
            raise ValueError("Server returned an unexpected CLI authorization URL")
        print("Open:", expected)
        print("Confirm this code in your own browser:", start["user_code"])
        if not args.no_browser:
            webbrowser.open(expected)
        deadline = time.monotonic() + min(600, int(start["expires_in"]))
        interval = max(5, int(start["interval"]))
        while time.monotonic() < deadline:
            time.sleep(interval)
            response = c.post(
                "/api/cli/device/poll",
                json={"device_code": start["device_code"], "verifier": verifier},
            )
            if response.status_code in {202, 429}:
                continue
            if response.status_code != 200:
                raise ValueError("CLI login was denied or expired. Start again.")
            data = response.json()
            save_session(
                path,
                {
                    "server": server,
                    "token": data["token"],
                    "id": data["id"],
                    "expires_at": data["expires_at"],
                    "scopes": data["scopes"],
                },
            )
            print("Signed in. Credential saved privately; expires in seven days.")
            return
    raise ValueError("CLI login timed out. Start again.")


def main():
    parser = argparse.ArgumentParser(
        prog="graphpilot", description="Connect to your hosted GraphPilot workspace"
    )
    parser.add_argument(
        "--config", type=Path, default=config_path(), help="Private CLI session file"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    auth = sub.add_parser("login", help="Approve CLI access in your browser")
    auth.add_argument("--server", required=True)
    auth.add_argument(
        "--write", action="store_true", help="Request repository management; default is read-only"
    )
    auth.add_argument("--no-browser", action="store_true")
    sub.add_parser("whoami")
    sub.add_parser("logout")
    repos = sub.add_parser("repos").add_subparsers(dest="action", required=True)
    repos.add_parser("list")
    connect = repos.add_parser("connect")
    connect.add_argument("url", nargs="?")
    connect.add_argument("--branch")
    connect.add_argument("--github-id", type=int)
    connect.add_argument("--installation", type=int)
    upload = repos.add_parser("upload")
    upload.add_argument("archive", type=Path)
    upload.add_argument("--branch", default="upload")
    for action in ["status", "check", "index", "sync"]:
        item = repos.add_parser(action)
        item.add_argument("repository_id")
    search = sub.add_parser("search")
    search.add_argument("repository_id")
    search.add_argument("query")
    evidence = sub.add_parser("evidence")
    evidence.add_argument("repository_id")
    evidence.add_argument("node_id")
    github = sub.add_parser("github").add_subparsers(dest="action", required=True)
    github.add_parser("installations")
    choices = github.add_parser("repos")
    choices.add_argument("installation", type=int)
    choices.add_argument("--page", type=int, default=1)
    args = parser.parse_args()
    try:
        if args.command == "login":
            login(args, args.config)
            return 0
        data = load_session(args.config)
        with httpx.Client(
            base_url=data["server"],
            headers={
                "Authorization": "Bearer " + data["token"],
                "Origin": data["server"],
                "Sec-Fetch-Site": "same-origin",
            },
            timeout=45,
            follow_redirects=False,
            trust_env=False,
        ) as c:
            if args.command == "whoami":
                result = call(c, "GET", "/api/auth/session")["user"]
            elif args.command == "logout":
                result = call(c, "POST", "/api/cli/logout")
                args.config.unlink()
            elif args.command == "github":
                route = "/api/integrations/github/installations"
                result = call(
                    c,
                    "GET",
                    route
                    if args.action == "installations"
                    else route + f"/{args.installation}/repositories",
                    params={} if args.action == "installations" else {"page": args.page},
                )
            elif args.command in {"search", "evidence"}:
                route = f"/api/repositories/{args.repository_id}"
                result = (
                    call(c, "GET", route + "/search", params={"q": args.query})
                    if args.command == "search"
                    else call(c, "GET", route + "/evidence/" + args.node_id)
                )
            elif args.action == "list":
                result = call(c, "GET", "/api/repositories")
            elif args.action == "connect":
                if args.github_id:
                    if not args.installation:
                        raise ValueError("Choose --installation with --github-id")
                    result = call(
                        c,
                        "POST",
                        "/api/integrations/github/repositories",
                        json={
                            "repository_id": args.github_id,
                            "installation_id": args.installation,
                            "branch": args.branch,
                        },
                    )
                else:
                    if not args.url:
                        raise ValueError(
                            "Supply a public GitHub URL, or --github-id and --installation"
                        )
                    result = call(
                        c,
                        "POST",
                        "/api/repositories",
                        json={
                            "source_type": "github",
                            "source": args.url,
                            "branch": args.branch or "main",
                        },
                    )
            elif args.action == "upload":
                if not args.archive.is_file() or args.archive.stat().st_size > 25_000_000:
                    raise ValueError("Choose a ZIP archive no larger than 25 MB")
                with args.archive.open("rb") as f:
                    result = call(
                        c,
                        "POST",
                        "/api/repositories/upload",
                        files={"file": (args.archive.name, f, "application/zip")},
                        data={"branch": args.branch},
                    )
            else:
                route = f"/api/repositories/{args.repository_id}"
                if args.action in {"index", "sync"}:
                    result = call(
                        c,
                        "POST",
                        route + "/jobs",
                        params={"kind": "index" if args.action == "index" else "github-sync"},
                    )
                elif args.action == "status":
                    result = {
                        "repository": call(c, "GET", route),
                        "jobs": call(c, "GET", route + "/jobs"),
                    }
                else:
                    result = {
                        "repository": call(c, "GET", route),
                        "jobs": call(c, "GET", route + "/jobs"),
                        "recorded_ci": call(
                            c, "GET", route + "/history", params={"kind": "WorkflowRun"}
                        ),
                        "notice": "Index and recorded CI checks only. Repository code is not executed.",
                    }
            print(json.dumps(result, indent=2))
        return 0
    except (ValueError, KeyError, OSError, httpx.HTTPError):
        # Do not echo response bodies, URLs with credentials, tokens or local file contents.
        print(
            "Command could not complete. Check your server URL, login, permissions and arguments.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
