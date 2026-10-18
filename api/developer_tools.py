"""Local developer workflows: a daily Git routine and gh-managed cloud runners.

These commands are intentionally local. They never read the GraphPilot CLI
session, never hit the hosted API and never expose a remote-shell endpoint.
Runners are the user's existing GitHub Codespaces, driven through the installed
GitHub CLI; profiles store only names and paths, never tokens.
"""

import json
import os
import re
import secrets
import shlex
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath

DEFAULT_WORKSPACE = "/workspaces/GraphPilot"
DEMO_PROJECT = "graphpilot-cloud-demo"
DEMO_STATE = f".data/cloud-demo/{DEMO_PROJECT}"
RUNNER_SERVICES = ("api", "worker", "web", "postgres", "falkordb")

_CODESPACE = re.compile(r"[a-z0-9-]{1,63}")
_PROFILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,62}")
_WORKSPACE = re.compile(r"/[A-Za-z0-9_./-]{1,199}")
_BRANCH = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_./-]{0,199}")
_USERINFO = re.compile(r"(https?://)[^\s/@]+@")
_QUERY_SECRET = re.compile(
    r"([?&][A-Za-z0-9._~-]*(?:token|key|secret|code|password|signature|sig|auth)"
    r"[A-Za-z0-9._~-]*=)[^&\s]*",
    re.I,
)
_KNOWN_TOKENS = re.compile(
    r"gp_mcp_[A-Za-z0-9_-]+|gh[a-z]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{16,}|"
    r"Bearer\s+[A-Za-z0-9._~+/=-]+",
    re.I,
)
_TOKENISH = re.compile(r"[A-Za-z0-9._~+/=-]{32,}")


class ToolError(Exception):
    """A concise, user-actionable failure."""


def _bounded(lower, upper):
    def parse(value):
        try:
            number = int(value)
        except ValueError:
            raise ValueError("must be an integer") from None
        if not lower <= number <= upper:
            raise ValueError(f"must be between {lower} and {upper}")
        return number

    return parse


def add_parsers(sub):
    git = sub.add_parser("git", help="Local daily Git workflow (no login required)")
    actions = git.add_subparsers(dest="action", required=True)

    def repo(action, help_text):
        p = actions.add_parser(action, help=help_text)
        p.add_argument("--path", type=Path, required=True, help="Path inside the repository")
        return p

    repo("daily", "Branch, status, upstream ahead/behind and recent commits")
    repo("status", "Short working-tree status")
    repo("diff", "Uncommitted changes against HEAD")
    log = repo("log", "Recent commits")
    log.add_argument("--count", type=_bounded(1, 100), default=10, metavar="1-100")
    switch = repo("switch", "Switch branches")
    switch.add_argument("branch")
    switch.add_argument("--create", action="store_true", help="Create the branch first")
    stage = repo("stage", "Stage files inside the repository")
    stage.add_argument("files", nargs="+", metavar="FILE")
    commit = repo("commit", "Commit staged content only")
    commit.add_argument("--message", required=True)
    repo("pull", "Fast-forward pull from the configured upstream")
    repo("push", "Normal push to the configured upstream (never forced)")

    runner = sub.add_parser(
        "runner", help="Manage your GitHub Codespace runner via gh (no login required)"
    )
    actions = runner.add_subparsers(dest="action", required=True)
    configure = actions.add_parser("configure", help="Store a named runner profile")
    configure.add_argument("name", help="Local profile name")
    configure.add_argument("--codespace", required=True, help="Exact gh Codespace name")
    configure.add_argument("--workspace", default=DEFAULT_WORKSPACE, help="Absolute repo path")
    actions.add_parser("list", help="List stored runner profiles")
    for action, help_text in [
        ("status", "Show gh-side Codespace state"),
        ("start", "Start the Codespace"),
        ("stop", "Stop the Codespace (explicit; stored profiles only)"),
        ("check", "Run the demo's fixed status+health check over SSH"),
        ("ssh", "Open an interactive SSH session"),
    ]:
        actions.add_parser(action, help=help_text).add_argument(
            "name", nargs="?", help="Profile name (required with several profiles)"
        )
    logs = actions.add_parser("logs", help="Bounded Docker Compose service logs over SSH")
    logs.add_argument("name", nargs="?", help="Profile name")
    logs.add_argument("--service", choices=RUNNER_SERVICES)
    logs.add_argument("--lines", type=_bounded(1, 5000), default=200, metavar="1-5000")


def dispatch(args):
    try:
        if args.command == "git":
            return _git_dispatch(args)
        if args.command == "runner":
            return _runner_dispatch(args)
    except ToolError as exc:
        print(exc, file=sys.stderr)
        return 1
    except (OSError, json.JSONDecodeError):
        # Never echo raw system/parse errors that may carry file contents.
        print(
            "Operation failed on local state; check file paths, permissions and profile syntax.",
            file=sys.stderr,
        )
        return 1
    return 2


# --- validation -----------------------------------------------------------


def _profile_name(name):
    if not _PROFILE.fullmatch(name):
        raise ToolError("Profile names are 1-63 characters of letters, digits, '.', '_' or '-'")
    return name


def _codespace(name):
    if not _CODESPACE.fullmatch(name) or name.startswith("-") or name.endswith("-"):
        raise ToolError(
            "Use the exact Codespace name shown by 'gh codespace list' "
            "(lowercase letters, digits and hyphens)"
        )
    return name


def _workspace(path):
    if not _WORKSPACE.fullmatch(path):
        raise ToolError("Workspace must be an absolute path such as /workspaces/GraphPilot")
    pure = PurePosixPath(path)
    if str(pure) != path or ".." in pure.parts:
        raise ToolError("Workspace must be a normalized absolute path without '..'")
    return path


def _ref(name):
    if (
        not _BRANCH.fullmatch(name)
        or ".." in name
        or "@{" in name
        or any(
            not part or part.startswith(".") or part.endswith((".", ".lock"))
            for part in name.split("/")
        )
    ):
        raise ToolError(f"Invalid branch name: {name!r}")
    return name


def _no_option(value):
    if value.startswith("-"):
        raise ToolError(f"Invalid argument: {value!r}")
    return value


# --- subprocess helpers -----------------------------------------------------


def _redact_run(match):
    token = match.group()
    if (
        re.fullmatch(r"[0-9a-fA-F]+", token)  # e.g. a commit SHA is useful, not secret
        or re.fullmatch(r"[0-9a-fA-F-]{36}", token)  # UUIDs
        or not re.search(r"[0-9]", token)
        or not re.search(r"[A-Za-z]", token)
        or not re.search(r"[._~+/=-]", token)
    ):
        return token
    return "REDACTED"


def _clean(text, limit=400):
    message = (text or "").strip()
    message = _USERINFO.sub(r"\1***@", message)
    message = _QUERY_SECRET.sub(r"\1REDACTED", message)
    message = _KNOWN_TOKENS.sub("REDACTED", message)
    message = _TOKENISH.sub(_redact_run, message)
    return message[:limit] if message else "no error output"


def _git(root, *args, timeout=60, literal=False):
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    if literal:
        env["GIT_LITERAL_PATHSPECS"] = "1"
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except FileNotFoundError:
        raise ToolError("git is not installed or not on PATH.") from None
    except subprocess.TimeoutExpired:
        raise ToolError(f"git {args[0]} timed out.") from None


def _git_run(root, *args, timeout=60, literal=False):
    result = _git(root, *args, timeout=timeout, literal=literal)
    if result.returncode:
        raise ToolError(f"git {args[0]} failed: {_clean(result.stderr)}")
    return result


def _git_checked(root, *args, timeout=60, literal=False):
    return _git_run(root, *args, timeout=timeout, literal=literal).stdout


def _repo(path):
    candidate = Path(path).expanduser()
    if not candidate.is_dir():
        raise ToolError(f"Not a directory: {candidate}")
    result = _git(candidate, "rev-parse", "--show-toplevel")
    if result.returncode:
        raise ToolError(f"Not a Git work tree: {candidate}")
    return Path(os.path.realpath(result.stdout.strip()))


def _gh(argv, timeout=90):
    try:
        return subprocess.run(["gh", *argv], capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise ToolError(
            "GitHub CLI 'gh' is not installed. Install it, then run 'gh auth login'."
        ) from None
    except subprocess.TimeoutExpired:
        raise ToolError("The gh command timed out. Check your connection and retry.") from None


def _gh_error(argv, stderr):
    message = _clean(stderr)
    if re.search(r"auth|login|credential|401|403|unauthor", message, re.I):
        return "GitHub authentication failed or expired. Run 'gh auth login'."
    return f"gh {' '.join(argv[:2])} failed: {message}"


def _gh_checked(argv, timeout=90):
    result = _gh(argv, timeout)
    if result.returncode:
        raise ToolError(_gh_error(argv, result.stderr))
    return result.stdout


def _list_codespaces(fields="name,state,repository,gitStatus"):
    output = _gh_checked(["codespace", "list", "--json", fields])
    try:
        found = json.loads(output or "[]")
    except json.JSONDecodeError:
        raise ToolError("gh returned unexpected output for 'codespace list'") from None
    if isinstance(found, dict):
        found = found.get("codespaces", [])
    return [item for item in found if isinstance(item, dict)]


def _require_available(name, profile):
    # `gh codespace ssh` silently starts a stopped Codespace; check/logs are
    # nominally read-only and must never wake a runner. `runner ssh` is the
    # explicit connect path and is allowed to.
    codespace = profile["codespace"]
    state = next(
        (
            item.get("state")
            for item in _list_codespaces("name,state")
            if item.get("name") == codespace
        ),
        None,
    )
    if state is None:
        raise ToolError(
            f"Codespace {codespace} is not visible to gh. "
            "Confirm it with 'gh codespace list' or fix the profile."
        )
    if state != "Available":
        raise ToolError(
            f"Runner '{name}' is {state}, not Available. "
            f"Start it explicitly first: 'graphpilot runner start {name}'."
        )


def _ssh(profile, remote=None, timeout=180):
    argv = ["gh", "codespace", "ssh", "-c", profile["codespace"]]
    interactive = remote is None
    if remote is not None:
        argv += ["--", remote]
    try:
        result = subprocess.run(
            argv,
            stderr=None if interactive else subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        raise ToolError(
            "GitHub CLI 'gh' is not installed. Install it, then run 'gh auth login'."
        ) from None
    except subprocess.TimeoutExpired:
        raise ToolError("The SSH session timed out.") from None
    if interactive:
        return result.returncode
    if result.returncode:
        raise ToolError(_gh_error(argv[1:3], result.stderr))
    return 0


# --- runner profiles --------------------------------------------------------


def _profiles_path(config):
    return config.parent / "runners.json"


def _save_profiles(path, data):
    if path.is_symlink():
        raise ToolError("Refusing a symlink for runner profiles")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    temporary = path.with_name("runners-" + secrets.token_hex(8) + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(data, stream)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _load_profiles(path):
    if not path.exists():
        return {"version": 1, "profiles": {}}
    meta = path.lstat()
    if not stat.S_ISREG(meta.st_mode) or meta.st_mode & 0o077 or meta.st_size > 65536:
        raise ToolError("Runner profile file must be a private regular file (mode 600)")
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        raise ToolError("Invalid runner profile file") from None
    if not isinstance(data, dict) or not isinstance(data.get("profiles"), dict):
        raise ToolError("Invalid runner profile file")
    for name, profile in data["profiles"].items():
        _profile_name(name)
        if not isinstance(profile, dict):
            raise ToolError("Invalid runner profile entry")
        _codespace(str(profile.get("codespace", "")))
        _workspace(str(profile.get("workspace", "")))
    return data


def _resolve(profiles, name):
    if name:
        profile = profiles.get(name)
        if profile is None:
            raise ToolError(f"No runner profile '{name}'. See 'graphpilot runner list'.")
        return name, profile
    if len(profiles) == 1:
        return next(iter(profiles.items()))
    if not profiles:
        raise ToolError(
            "No runners configured. Run 'graphpilot runner configure NAME --codespace CODESPACE'."
        )
    raise ToolError("Several runners are configured; specify NAME (see 'graphpilot runner list').")


def _runner_dispatch(args):
    path = _profiles_path(args.config)
    if args.action == "configure":
        store = _load_profiles(path)
        store["profiles"][_profile_name(args.name)] = {
            "codespace": _codespace(args.codespace),
            "workspace": _workspace(args.workspace),
        }
        _save_profiles(path, store)
        print(json.dumps({"profile": args.name, **store["profiles"][args.name]}, indent=2))
        return 0
    store = _load_profiles(path)
    if args.action == "list":
        print(json.dumps(store["profiles"], indent=2))
        return 0
    if args.action == "status":
        names = [args.name] if args.name else list(store["profiles"])
        if not names:
            raise ToolError(
                "No runners configured. Run 'graphpilot runner configure NAME --codespace CODESPACE'."
            )
        selected = {name: _resolve(store["profiles"], name)[1] for name in names}
        found = _list_codespaces()
        wanted = {p["codespace"]: name for name, p in selected.items()}
        matches = [
            {
                "name": item.get("name"),
                "state": item.get("state"),
                "repository": item.get("repository"),
                "profile": wanted[item["name"]],
            }
            for item in found
            if item.get("name") in wanted
        ]
        missing = [
            name
            for name, p in selected.items()
            if p["codespace"] not in {m["name"] for m in matches}
        ]
        print(json.dumps({"runners": matches, "not_found": missing}, indent=2))
        return 0
    name, profile = _resolve(store["profiles"], args.name)
    codespace = profile["codespace"]
    if args.action == "start":
        _gh_checked(["api", "-X", "POST", f"/user/codespaces/{codespace}/start", "--silent"])
        print(f"Runner '{name}' start requested (Codespace {codespace}).")
        return 0
    if args.action == "stop":
        _gh_checked(["codespace", "stop", "-c", codespace])
        print(f"Runner '{name}' stopped (Codespace {codespace}).")
        return 0
    if args.action == "ssh":
        return _ssh(profile, timeout=None)
    workspace = profile["workspace"]
    if args.action == "check":
        _require_available(name, profile)
        remote = (
            f"cd {shlex.quote(workspace)} && "
            "python3 scripts/cloud_demo.py status && "
            "python3 scripts/cloud_demo.py check"
        )
        _ssh(profile, remote)
        return 0
    if args.action == "logs":
        _require_available(name, profile)
        remote = (
            f"cd {shlex.quote(workspace)} && docker compose "
            f"--env-file {shlex.quote(DEMO_STATE + '/compose.env')} "
            f"-p {DEMO_PROJECT} -f docker-compose.yml "
            f"-f {shlex.quote(DEMO_STATE + '/override.json')} "
            f"logs --no-color --tail {args.lines}"
        )
        if args.service:
            remote += f" {args.service}"
        _ssh(profile, remote)
        return 0
    raise ToolError(f"Unknown runner action: {args.action}")


# --- git workflow -----------------------------------------------------------


def _emit(result):
    output = (result.stdout or "").rstrip()
    errors = (result.stderr or "").rstrip()
    if output:
        print(output)
    if errors:
        print(_clean(errors, limit=2000), file=sys.stderr)


def _has_head(root):
    return _git(root, "rev-parse", "--verify", "HEAD").returncode == 0


def _daily(root):
    branch = _git(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    name = branch.stdout.strip() if not branch.returncode else "HEAD (detached)"
    dirty = _git_checked(root, "status", "--porcelain").splitlines()
    print(f"branch: {name}")
    print(f"status: {'clean' if not dirty else f'{len(dirty)} changed file(s)'}")
    upstream = _git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    if upstream.returncode:
        print("upstream: none configured")
    else:
        counts = _git_checked(
            root, "rev-list", "--left-right", "--count", "@{upstream}...HEAD"
        ).split()
        print(f"upstream: {upstream.stdout.strip()} (ahead {counts[1]}, behind {counts[0]})")
    if _has_head(root):
        print("recent commits:")
        print(_git_checked(root, "log", "--format=  %h %s", "-n", "5"), end="")
    if dirty:
        shown = dirty[:20]
        print("changed files:")
        print("\n".join("  " + line for line in shown))
        if len(dirty) > len(shown):
            print(f"  ... and {len(dirty) - len(shown)} more")


def _git_dispatch(args):
    root = _repo(args.path)
    action = args.action
    if action == "daily":
        _daily(root)
        return 0
    if action == "status":
        print(_git_checked(root, "status", "--short", "--branch"), end="")
        return 0
    if action == "diff":
        target = ["HEAD"] if _has_head(root) else []
        _emit(_git_run(root, "diff", *target, "--"))
        return 0
    if action == "log":
        if not _has_head(root):
            print("No commits yet.")
            return 0
        print(_git_checked(root, "log", "--format=%h %s", "-n", str(args.count)), end="")
        return 0
    if action == "switch":
        branch = _ref(args.branch)
        argv = ["switch", "--create", branch] if args.create else ["switch", branch]
        _emit(_git_run(root, *argv))
        return 0
    if action == "stage":
        real = Path(os.path.realpath(root))
        base = Path(os.path.realpath(args.path))
        paths = []
        for item in args.files:
            _no_option(item)
            given = Path(item)
            candidate = given if given.is_absolute() else base / given
            lexical = Path(os.path.normpath(candidate))
            if not lexical.is_relative_to(real) or not Path(
                os.path.realpath(candidate)
            ).is_relative_to(real):
                raise ToolError(f"Cannot stage outside the repository: {item!r}")
            relative = lexical.relative_to(real).as_posix()
            if relative == ".git" or relative.startswith(".git/"):
                raise ToolError(f"Cannot stage .git internals: {item!r}")
            paths.append(relative)
        _git_checked(root, "add", "--", *paths, literal=True)
        print(f"Staged {len(paths)} path(s).")
        return 0
    if action == "commit":
        if not args.message.strip():
            raise ToolError("Supply a non-empty commit message")
        _emit(_git_run(root, "commit", "--message", args.message))
        return 0
    if action == "pull":
        _emit(_git_run(root, "pull", "--ff-only", timeout=120))
        return 0
    if action == "push":
        _emit(_git_run(root, "push", timeout=120))
        return 0
    raise ToolError(f"Unknown git action: {action}")
