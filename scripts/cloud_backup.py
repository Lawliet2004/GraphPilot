"""Protected Compose backup and optional isolated restore drill.

Quiesces and restarts only the named GraphPilot stack; no live volume is removed.
Backups contain private credentials/source. Keep them private and copy off-host.
"""

import argparse
import hashlib
import io
import json
import os
import re
import secrets
import subprocess
import tarfile
import time
from pathlib import Path

FINGERPRINT = r"""
import hashlib,json,os
from pathlib import Path
from sqlalchemy import inspect,text
from api.db import engine
from api.graph.store import client,query
from api.config import settings
out={'tables':{},'graphs':{},'artifacts':{}}
with engine.connect() as c:
 for table in sorted(inspect(engine).get_table_names()):
  if not table.replace('_','').isalnum(): raise RuntimeError('Invalid SQL identifier')
  rows=[json.dumps(dict(r),sort_keys=True,default=str) for r in c.execute(text('SELECT * FROM "'+table+'"')).mappings()]
  out['tables'][table]={'rows':len(rows),'sha256':hashlib.sha256('\n'.join(sorted(rows)).encode()).hexdigest()}
for name in sorted(client().list_graphs()):
 out['graphs'][name]={'nodes':query(name,'MATCH (n) RETURN count(n)')[0][0], 'edges':query(name,'MATCH ()-[r]->() RETURN count(r)')[0][0]}
root=settings().data_dir
for group in ('snapshots','uploads','logs'):
 for path in sorted((root/group).rglob('*')):
  if path.is_symlink(): raise RuntimeError('Unexpected artifact symlink')
  if path.is_file(): out['artifacts'][str(path.relative_to(root))]=hashlib.sha256(path.read_bytes()).hexdigest()
print(json.dumps(out,sort_keys=True))
"""


def validate_archive(data):
    with tarfile.open(fileobj=io.BytesIO(data)) as tf:
        for m in tf:
            p = Path(m.name)
            if p.is_absolute() or ".." in p.parts or not (m.isdir() or m.isfile()):
                raise RuntimeError("Unsafe backup archive member")


ROOT = Path(__file__).resolve().parents[1]


def validate_project(project):
    if not isinstance(project, str) or not re.fullmatch(r"graphpilot-cloud-[a-z0-9-]+", project):
        raise ValueError("Use an owned graphpilot-cloud-* Compose project")
    return project


def private_write(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(data.encode() if isinstance(data, str) else data)


def load_backup(directory):
    expected = {
        "postgres.dump",
        "falkor.tar",
        "artifacts.tar",
        "runtime.env",
        "fingerprint.json",
        "metadata.json",
    }
    manifest_path = directory / "manifest.json"
    if directory.is_symlink() or directory.stat().st_mode & 0o077:
        raise ValueError("Backup directory must be owner-only")
    if (
        manifest_path.is_symlink()
        or not manifest_path.is_file()
        or manifest_path.stat().st_mode & 0o077
    ):
        raise ValueError("Backup manifest must be a private regular file")
    manifest = json.loads(manifest_path.read_text())
    if not isinstance(manifest, dict) or set(manifest) != expected:
        raise ValueError("Unexpected backup manifest")
    result = {}
    for name, digest in manifest.items():
        path = directory / name
        if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
            raise ValueError("Backup files must be private regular files")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError("Backup checksum mismatch")
        result[name] = data
    validate_archive(result["falkor.tar"])
    validate_archive(result["artifacts.tar"])
    return result


def require_ownership(info, project):
    labels = info.get("Labels") or info.get("Config", {}).get("Labels") or {}
    if labels.get("com.docker.compose.project") != project:
        raise RuntimeError("Docker resource ownership mismatch")


def require_fresh_target(run, project):
    if run(
        ["docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=" + project]
    ).strip():
        raise RuntimeError("Restore target already exists")
    if run(
        ["docker", "volume", "ls", "-q", "--filter", "label=com.docker.compose.project=" + project]
    ).strip():
        raise RuntimeError("Restore target volumes already exist")


def backup_metadata(saved):
    metadata = json.loads(saved["metadata.json"])
    if not isinstance(metadata, dict):
        raise ValueError("Invalid backup metadata")
    validate_project(metadata.get("source_project", ""))
    images = metadata.get("images", {})
    if (
        metadata.get("format_version") != 1
        or not isinstance(images, dict)
        or any(
            not isinstance(images.get(name), str)
            or not re.fullmatch(r"sha256:[a-f0-9]{64}", images[name])
            for name in ("api", "postgres", "falkordb")
        )
    ):
        raise ValueError("Invalid backup image metadata")
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default="graphpilot-cloud-demo", type=validate_project)
    restore = parser.add_mutually_exclusive_group()
    restore.add_argument(
        "--restore-drill",
        action="store_true",
        help="Also restore into a new private project, verify data, then remove only that target",
    )
    restore.add_argument(
        "--restore-backup",
        type=Path,
        help="Verify and restore an existing private backup into a disposable isolated target",
    )
    args = parser.parse_args()
    os.umask(0o077)
    SOURCE = args.project
    STATE = ROOT / ".data/cloud-demo" / SOURCE
    RUN = secrets.token_hex(5)
    TARGET = "graphpilot-restore-" + RUN
    if args.restore_backup:
        BACKUP = args.restore_backup.absolute()
        saved = load_backup(BACKUP)
        metadata = backup_metadata(saved)
        SOURCE = validate_project(metadata.get("source_project", ""))
    else:
        if any(
            p.is_symlink()
            for p in (
                ROOT / ".data",
                STATE.parent,
                STATE,
                STATE / "compose.env",
                STATE / "override.json",
                ROOT / ".data/backups",
            )
        ):
            raise ValueError("Private deployment and backup paths must not be symlinks")
        if not (STATE / "compose.env").is_file() or not (STATE / "override.json").is_file():
            raise ValueError("Start this owned GraphPilot project before backing it up")
        BACKUP = ROOT / ".data/backups" / ("cloud-" + RUN)
        BACKUP.mkdir(parents=True, mode=0o700)
        BACKUP.chmod(0o700)
    ENV = {**os.environ, "GP_ENV_FILE": str(STATE / "compose.env")}
    for k in ("GP_WEB_PORT", "POSTGRES_PASSWORD", "GP_COMPOSE_DATABASE_URL"):
        ENV.pop(k, None)
    BASE = [
        "docker",
        "compose",
        "--env-file",
        str(STATE / "compose.env"),
        "-p",
        SOURCE,
        "-f",
        str(ROOT / "docker-compose.yml"),
        "-f",
        str(STATE / "override.json"),
    ]
    report = {
        "source_project": SOURCE,
        "target_project": TARGET,
        "status": "started",
        "scope": (
            "existing backup isolated restore"
            if args.restore_backup
            else "backup and isolated restore"
            if args.restore_drill
            else "backup only"
        ),
    }

    def run(cmd, *, data=None, timeout=180):
        p = subprocess.run(cmd, input=data, capture_output=True, cwd=ROOT, env=ENV, timeout=timeout)
        if p.returncode:
            private_write(BACKUP / "last-error.txt", p.stderr)
            raise RuntimeError("Command failed: " + Path(cmd[0]).name)
        return p.stdout

    def compose(*args, data=None):
        return run(BASE + list(args), data=data)

    def archive(volume, image):
        info = json.loads(run(["docker", "volume", "inspect", volume]))[0]
        require_ownership(info, SOURCE)
        return run(
            [
                "docker",
                "run",
                "--rm",
                "--user",
                "0:0",
                "--network",
                "none",
                "--volume",
                volume + ":/volume:ro",
                "--entrypoint",
                "tar",
                image,
                "-C",
                "/volume",
                "-cf",
                "-",
                ".",
            ]
        )

    stopped = []
    target_base = None
    if not args.restore_backup:
        try:
            containers = [
                json.loads(x) for x in compose("ps", "--format", "json").splitlines() if x
            ]
            running = {x["Service"] for x in containers if x["State"] == "running"}
            if not {"api", "worker", "web", "postgres", "falkordb"} <= running:
                raise RuntimeError("Expected healthy owned live services")
            api_id = compose("ps", "-q", "api").decode().strip()
            info = json.loads(run(["docker", "inspect", api_id]))[0]
            require_ownership(info, SOURCE)
            api_image = info["Image"]
            pg_id = compose("ps", "-q", "postgres").decode().strip()
            info = json.loads(run(["docker", "inspect", pg_id]))[0]
            require_ownership(info, SOURCE)
            pg_image = info["Image"]
            graph_id = compose("ps", "-q", "falkordb").decode().strip()
            info = json.loads(run(["docker", "inspect", graph_id]))[0]
            require_ownership(info, SOURCE)
            graph_image = info["Image"]
            active = compose(
                "exec",
                "-T",
                "api",
                "python",
                "-c",
                "from api.db import SessionLocal; from api.models import Job; from sqlalchemy import select,func; d=SessionLocal(); print(d.scalar(select(func.count()).select_from(Job).where(Job.status.in_(['queued','running']))))",
            )
            if int(active):
                raise RuntimeError("Active jobs must finish before maintenance")
            for service in ("web", "api", "worker"):
                stopped.append(service)
                compose("stop", service)
            active = compose(
                "run",
                "--rm",
                "--no-deps",
                "-T",
                "api",
                "python",
                "-c",
                "from api.db import SessionLocal; from api.models import Job; from sqlalchemy import select,func; d=SessionLocal(); print(d.scalar(select(func.count()).select_from(Job).where(Job.status.in_(['queued','running']))))",
            )
            if int(active):
                raise RuntimeError("Jobs appeared before ingress quiesced; retry later")
            before = json.loads(
                compose("run", "--rm", "--no-deps", "-T", "api", "python", "-c", FINGERPRINT)
            )
            if not before["graphs"] or not before["artifacts"]:
                raise RuntimeError("No meaningful graph/artifact data to recover")
            dump = compose(
                "exec",
                "-T",
                "postgres",
                "sh",
                "-c",
                'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-privileges',
            )
            compose("exec", "-T", "falkordb", "redis-cli", "SAVE")
            stopped.append("falkordb")
            compose("stop", "falkordb")
            stopped.append("postgres")
            compose("stop", "postgres")
            graph = archive(SOURCE + "_falkor_data", api_image)
            artifacts = archive(SOURCE + "_artifacts", api_image)
            validate_archive(graph)
            validate_archive(artifacts)
            for name, data in [
                ("postgres.dump", dump),
                ("falkor.tar", graph),
                ("artifacts.tar", artifacts),
                ("runtime.env", (STATE / "compose.env").read_bytes()),
                ("fingerprint.json", json.dumps(before, sort_keys=True).encode()),
                (
                    "metadata.json",
                    json.dumps(
                        {
                            "format_version": 1,
                            "source_commit": run(["git", "rev-parse", "HEAD"]).decode().strip(),
                            "images": {
                                "api": api_image,
                                "postgres": pg_image,
                                "falkordb": graph_image,
                            },
                            "source_project": SOURCE,
                        }
                    ).encode(),
                ),
            ]:
                private_write(BACKUP / name, data)
            checksums = {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in BACKUP.iterdir()
                if p.is_file()
            }
            private_write(BACKUP / "manifest.json", json.dumps(checksums, indent=2) + "\n")
            report["backup_created"] = True
        finally:
            if stopped:
                failed = []
                for service in reversed(stopped):
                    try:
                        compose("start", service)
                    except (RuntimeError, OSError, subprocess.SubprocessError):
                        failed.append(service)
                if failed:
                    raise RuntimeError(
                        "Some owned services could not resume; inspect the live stack"
                    )

    if not (args.restore_drill or args.restore_backup):
        report.update(status="passed", source_services_resumed=True, backup_directory=str(BACKUP))
        private_write(BACKUP / "report.json", json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
        return

    try:
        saved = load_backup(BACKUP)
        metadata = backup_metadata(saved)
        images = metadata.get("images", {})
        api_image, pg_image, graph_image = (
            images[name] for name in ("api", "postgres", "falkordb")
        )
        dump, graph, artifacts = (
            saved[name] for name in ("postgres.dump", "falkor.tar", "artifacts.tar")
        )
        before = json.loads(saved["fingerprint.json"])
        target_env = BACKUP / "restore.env"
        vals = dict(
            line.split("=", 1)
            for line in (BACKUP / "runtime.env").read_text().splitlines()
            if "=" in line and not line.startswith("#")
        )
        vals.update(
            {
                "GP_ENVIRONMENT": "development",
                "GP_COOKIE_SECURE": "false",
                "GP_PUBLIC_URL": "http://localhost",
                "GP_ORIGINS": '["http://localhost"]',
                "GP_DATABASE_URL": vals["GP_COMPOSE_DATABASE_URL"],
                "GP_DATA_DIR": "/data",
                "GP_FALKOR_HOST": "falkordb",
                "GP_FALKOR_PORT": "6379",
                "GP_FIREBASE_PROJECT_ID": "",
                "GP_FIREBASE_API_KEY": "",
                "GP_GITHUB_CLIENT_ID": "",
                "GP_GITHUB_CLIENT_SECRET": "",
                "GP_GITHUB_APP_SLUG": "",
                "GP_GITHUB_TOKEN": "",
                "GP_LLM_BASE_URL": "",
                "GP_LLM_MODEL": "",
                "GP_LLM_API_KEY": "",
            }
        )
        private_write(target_env, "\n".join(k + "=" + v for k, v in vals.items()) + "\n")
        config = {
            "services": {
                "postgres": {
                    "image": pg_image,
                    "environment": {
                        k: vals[k] for k in ["POSTGRES_USER", "POSTGRES_DB", "POSTGRES_PASSWORD"]
                    },
                    "volumes": ["postgres_data:/var/lib/postgresql"],
                    "networks": ["private"],
                },
                "falkordb": {
                    "image": graph_image,
                    "user": "redis",
                    "entrypoint": ["redis-server"],
                    "command": [
                        "--loadmodule",
                        "/var/lib/falkordb/bin/falkordb.so",
                        "--protected-mode",
                        "no",
                        "--appendonly",
                        "yes",
                        "--dir",
                        "/data",
                    ],
                    "volumes": ["falkor_data:/data"],
                    "networks": ["private"],
                },
                "api": {
                    "image": api_image,
                    "env_file": [str(target_env)],
                    "volumes": ["artifacts:/data"],
                    "networks": ["private"],
                },
            },
            "volumes": {"postgres_data": {}, "falkor_data": {}, "artifacts": {}},
            "networks": {"private": {"internal": True}},
        }
        target_file = BACKUP / "restore.json"
        private_write(target_file, json.dumps(config))
        require_fresh_target(run, TARGET)
        target_base = ["docker", "compose", "-p", TARGET, "-f", str(target_file)]
        run(target_base + ["create"])
        for suffix, data in [("falkor_data", graph), ("artifacts", artifacts)]:
            volume = TARGET + "_" + suffix
            info = json.loads(run(["docker", "volume", "inspect", volume]))[0]
            require_ownership(info, TARGET)
            run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-i",
                    "--user",
                    "0:0",
                    "--network",
                    "none",
                    "--volume",
                    volume + ":/volume",
                    "--entrypoint",
                    "tar",
                    api_image,
                    "-C",
                    "/volume",
                    "-xf",
                    "-",
                ],
                data=data,
            )
        run(target_base + ["start", "postgres", "falkordb"])
        for _attempt in range(60):
            p = subprocess.run(
                target_base
                + [
                    "exec",
                    "-T",
                    "postgres",
                    "sh",
                    "-c",
                    'test "$(cat /proc/1/comm)" = postgres && pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"',
                ],
                capture_output=True,
            )
            if p.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("Restore PostgreSQL readiness timed out")
        run(
            target_base
            + [
                "exec",
                "-T",
                "postgres",
                "sh",
                "-c",
                'pg_restore --exit-on-error --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB"',
            ],
            data=dump,
        )
        after = json.loads(
            run(
                target_base + ["run", "--rm", "--no-deps", "-T", "api", "python", "-c", FINGERPRINT]
            )
        )
        if before != after:
            raise RuntimeError("Restore fingerprint mismatch")
        run(target_base + ["start", "api"])
        health = False
        for _attempt in range(40):
            try:
                value = run(
                    target_base
                    + [
                        "exec",
                        "-T",
                        "api",
                        "python",
                        "-c",
                        "import json,urllib.request; print(json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/health/ready',timeout=5))['status'])",
                    ]
                )
                if value.strip() == b"ready":
                    health = True
                    break
            except RuntimeError:
                pass
            time.sleep(1)
        if not health:
            raise RuntimeError("Restored API readiness failed")
        report.update(
            status="passed",
            sql_tables_equal=len(before["tables"]),
            graphs_equal=len(before["graphs"]),
            artifact_files_equal=len(before["artifacts"]),
            isolated_api_ready=True,
            source_services_touched=not bool(args.restore_backup),
            backup_directory=str(BACKUP),
        )
    finally:
        try:
            if target_base:
                try:
                    run(target_base + ["down", "--volumes", "--remove-orphans"])
                except (RuntimeError, OSError, subprocess.SubprocessError):
                    report["status"] = "target_cleanup_failed"
                    raise
                report["isolated_target_removed"] = True
        finally:
            # Retain private config for manual cleanup only if Docker cleanup failed.
            if not target_base or report.get("isolated_target_removed"):
                for name in ("restore.env", "restore.json"):
                    (BACKUP / name).unlink(missing_ok=True)
            private_write(BACKUP / "report.json", json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as exc:
        raise SystemExit(
            "Backup/restore failed ("
            + type(exc).__name__
            + "). Inspect private backup logs and live service state."
        ) from None
