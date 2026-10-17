"""Strict source adapters. Repository content is data and is never executed."""

import os
import re
import shutil
import signal
import stat
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from api.config import settings

IGNORED = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "vendor",
    "dist",
    "build",
    ".tox",
    ".mypy_cache",
}


class SourceError(ValueError):
    pass


def validate_branch(branch):
    if (
        not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_./-]{0,199}", branch)
        or ".." in branch
        or any(
            not part or part.startswith(".") or part.endswith((".", ".lock"))
            for part in branch.split("/")
        )
    ):
        raise SourceError("Enter a valid Git branch name")
    return branch


def github_url(value: str) -> str:
    url = urlsplit(value)
    if (
        url.scheme != "https"
        or url.hostname != "github.com"
        or url.port
        or url.username
        or url.password
        or url.query
        or url.fragment
    ):
        raise SourceError("Use a public https://github.com/owner/repository URL")
    match = re.fullmatch(r"/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?", url.path)
    if not match or any(p in {".", ".."} or p.startswith("-") for p in match.groups()):
        raise SourceError("Use a public https://github.com/owner/repository URL")
    return f"https://github.com/{match[1]}/{match[2]}"


def local_path(value: str) -> Path:
    path = Path(value).resolve(strict=True)
    roots = [p.resolve() for p in settings().allowed_local_roots]
    if not roots or not any(path.is_relative_to(root) for root in roots):
        raise SourceError("Server-local access is not enabled for this directory")
    if not path.is_dir() or not (path / ".git").exists():
        raise SourceError("Choose a Git repository within a configured allowed root")
    return path


def git(path: Path, *args, timeout=30, raw=False):
    env = {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_LFS_SKIP_SMUDGE": "1",
    }
    # Disable hooks, external filters, filesystem monitor and protocol helpers.
    command = [
        "git",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "protocol.file.allow=never",
        "-c",
        "protocol.ext.allow=never",
        "-C",
        str(path),
        *args,
    ]
    deadline = time.monotonic() + timeout
    limit = settings().max_extract_bytes
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(
            command, env=env, stdout=stdout, stderr=stderr, start_new_session=True
        )
        try:
            # Limit the Git process as well as the resulting snapshot. A bare fetch
            # cannot write an unbounded pack before the post-download validation.
            import resource

            try:
                resource.prlimit(process.pid, resource.RLIMIT_FSIZE, (limit, limit))
                resource.prlimit(process.pid, resource.RLIMIT_AS, (768 * 2**20, 768 * 2**20))
            except ProcessLookupError:
                pass  # A short read-only Git command may already have completed.
            fetching = "fetch" in args
            while process.poll() is None:
                if time.monotonic() > deadline:
                    raise SourceError("Git operation exceeded its time limit")
                if fetching:
                    size = 0
                    for base, dirs, names in os.walk(path, followlinks=False):
                        dirs[:] = [d for d in dirs if not Path(base, d).is_symlink()]
                        for name in names:
                            candidate = Path(base, name)
                            try:
                                if not candidate.is_symlink():
                                    size += candidate.stat().st_size
                            except FileNotFoundError:
                                continue
                    if size > limit:
                        raise SourceError("Repository exceeds download storage limit")
                time.sleep(0.02)
            if process.returncode != 0:
                raise SourceError(
                    "Git operation failed or exceeded its resource limit. Check source and branch."
                )
            stdout.seek(0)
            data = stdout.read(limit + 1)
            if len(data) > limit:
                raise SourceError("Git output exceeds the source size limit")
            return data if raw else data.decode("utf-8", errors="replace").strip()
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait()


def extract_zip(archive: Path, destination: Path):
    cfg = settings()
    destination.mkdir(parents=True, exist_ok=True)
    total = 0
    try:
        with zipfile.ZipFile(archive) as zf:
            entries = zf.infolist()
            if len(entries) > cfg.max_files * 2:
                raise SourceError("Archive has too many entries")
            paths = set()
            for info in entries:
                path = PurePosixPath(info.filename)
                mode = info.external_attr >> 16
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or "\\" in info.filename
                    or not path.parts
                    or ":" in path.parts[0]
                    or stat.S_ISLNK(mode)
                ):
                    raise SourceError("Archive contains an unsafe path or symbolic link")
                if any(p in IGNORED for p in path.parts):
                    continue
                if str(path) in paths:
                    raise SourceError("Archive contains duplicate file paths")
                paths.add(str(path))
                total += info.file_size
                if total > cfg.max_extract_bytes or info.file_size > cfg.max_file_bytes:
                    raise SourceError("Archive exceeds extraction limits")
                target = destination.joinpath(*path.parts)
                if not target.resolve().is_relative_to(destination.resolve()):
                    raise SourceError("Archive escapes extraction directory")
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(info) as src, target.open("wb") as dst:
                        remaining = info.file_size
                        while chunk := src.read(min(65536, remaining + 1)):
                            remaining -= len(chunk)
                            if remaining < 0:
                                raise SourceError("Invalid archive size")
                            dst.write(chunk)
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError):
        raise SourceError("Upload a valid, unencrypted ZIP archive") from None


def snapshot(source_type: str, source: str, branch: str, destination: Path):
    """Return commit, branch and safe immutable text files. Never checkout local trees."""
    cfg = settings()
    destination.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    if source_type == "archive":
        extract_zip(Path(source), destination)
        commit = "archive"
    else:
        validate_branch(branch)
        if source_type == "local":
            repo = local_path(source)
        else:
            url = github_url(source)
            repo = destination.parent / "checkout"
            # Fetch into a new bare repository: no checkout filters, submodules, hooks or LFS.
            if repo.exists():
                shutil.rmtree(repo)
            repo.mkdir()
            git(repo, "init", "--bare")
            git(
                repo,
                "-c",
                "http.followRedirects=false",
                "-c",
                "http.maxRequests=2",
                "fetch",
                "--depth=100",
                "--no-tags",
                url,
                f"refs/heads/{branch}:refs/heads/{branch}",
                timeout=cfg.job_timeout_seconds,
            )
            if (
                sum(p.stat().st_size for p in repo.rglob("*") if p.is_file())
                > cfg.max_extract_bytes
            ):
                raise SourceError("Repository exceeds download storage limit")
        commit = git(repo, "rev-parse", "--verify", f"refs/heads/{branch}^{{commit}}")
        tree = git(repo, "ls-tree", "-r", "-z", "--long", commit)
        entries = tree.split("\0")
        count, total = 0, 0
        for entry in entries:
            if not entry:
                continue
            metadata, path = entry.split("\t", 1)
            mode, kind, oid, size = metadata.split()
            parts = PurePosixPath(path).parts
            if (
                mode not in {"100644", "100755"}
                or kind != "blob"
                or any(p in IGNORED for p in parts)
            ):
                continue
            if ".." in parts or PurePosixPath(path).is_absolute():
                raise SourceError("Unsafe Git tree path")
            count += 1
            if count > cfg.max_files:
                raise SourceError("Repository exceeds file count limit")
            if int(size) > cfg.max_file_bytes:
                continue
            total += int(size)
            if (
                total > cfg.max_extract_bytes
                or time.monotonic() - started > cfg.job_timeout_seconds
            ):
                raise SourceError("Repository exceeds indexing resource limit")
            # Blob IDs cannot be options or arbitrary refs (validated by Git ls-tree).
            data = git(repo, "cat-file", "blob", oid, raw=True)
            if b"\x00" in data:
                continue
            target = destination.joinpath(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    return commit, branch


def read_files(root: Path) -> dict[str, str]:
    import pathspec

    cfg = settings()
    # Keep per-directory rule precedence and explicit negations. A nested ignore
    # file cannot re-include anything below a directory already pruned by its parent.
    scopes = {}
    ignore_bytes, ignore_patterns, walked = 0, 0, 0
    files, total = {}, 0
    for base, dirs, names in os.walk(root, followlinks=False):
        directory = Path(base)
        walked += 1
        if walked > cfg.max_files * 4:
            raise SourceError("Repository exceeds directory traversal limit")
        rules = list(scopes.pop(directory, []))
        ignore = directory / ".gitignore"
        if ignore.is_file() and not ignore.is_symlink():
            size = ignore.stat().st_size
            ignore_bytes += size
            if size > 65536 or ignore_bytes > 262144:
                raise SourceError("Repository ignore rules exceed size limit")
            lines = ignore.read_text(errors="replace").splitlines()
            ignore_patterns += len(lines)
            if ignore_patterns > 4096:
                raise SourceError("Repository has too many ignore rules")
            rules.append((directory, pathspec.GitIgnoreSpec.from_lines(lines)))

        def ignored(path, is_directory=False, rules=tuple(rules)):
            excluded = False
            for scope, spec in rules:
                result = spec.check_file(
                    path.relative_to(scope).as_posix() + ("/" if is_directory else "")
                )
                if result.include is not None:
                    excluded = result.include
            return excluded

        dirs[:] = sorted(
            d
            for d in dirs
            if d not in IGNORED
            and not (directory / d).is_symlink()
            and not ignored(directory / d, True)
        )
        for child in dirs:
            scopes[directory / child] = rules
        for name in sorted(names):
            path = Path(base, name)
            rel = path.relative_to(root).as_posix()
            if path.is_symlink() or ignored(path) or path.stat().st_size > cfg.max_file_bytes:
                continue
            if len(files) >= cfg.max_files:
                raise SourceError("Repository exceeds file count limit")
            raw = path.read_bytes()
            if b"\0" in raw:
                continue
            total += len(raw)
            if total > cfg.max_extract_bytes:
                raise SourceError("Repository exceeds text size limit")
            try:
                files[rel] = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
    return files


def prune_snapshot(root, included):
    """Retain only the exact indexed text files in published source artifacts."""
    for base, dirs, files in os.walk(root, topdown=False, followlinks=False):
        for name in files:
            path = Path(base, name)
            if path.relative_to(root).as_posix() not in included:
                path.unlink()
        for name in dirs:
            path = Path(base, name)
            if path.is_symlink():
                path.unlink()
            elif not any(path.iterdir()):
                path.rmdir()
