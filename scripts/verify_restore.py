"""Native-only, isolated restore drill for this project's owned development stack.

Stops/restarts only exact workspace API/worker processes, creates a private backup,
restores into a new database and separate real FalkorDBLite, and tests via HTTP.
Never restores over the original databases or source artifacts.
"""

import hashlib
import io
import json
import os
import secrets
import shutil
import signal
import subprocess
import tarfile
import time
import uuid
import zipfile
from pathlib import Path

import httpx
import psutil
from redislite.falkordb_client import FalkorDB
from sqlalchemy import create_engine, delete, select, text

from api.config import settings
from api.db import SessionLocal, engine, utcnow
from api.graph import store
from api.models import Job, Repository, User
from scripts.maintenance import assert_no_browser_tests


def wait_ready(url):
    for _ in range(100):
        try:
            if httpx.get(url + "/api/health/ready", timeout=2).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise RuntimeError("HTTP service did not become ready during restore drill")


def stop_group(process):
    if process and process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


def main():
    cfg, project = settings(), Path.cwd().resolve()
    assert_no_browser_tests(project)
    assert cfg.environment == "development" and engine.url.host == "127.0.0.1"
    assert engine.url.port == 55432 and cfg.falkor_port == 56379 and not cfg.falkor_socket
    source_root = cfg.data_dir.resolve()
    assert source_root == project / ".data", "Drill is restricted to this owned native workspace"
    python = str(project / ".venv/bin/python")
    expected = {
        "api": [
            python,
            str(project / ".venv/bin/uvicorn"),
            "api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
            "--no-access-log",
        ],
        "worker": [python, "-m", "api.worker"],
    }
    services = {}
    for proc in psutil.process_iter(["cmdline"]):
        for name, command in expected.items():
            if proc.info["cmdline"] == command:
                services[name] = (proc, proc.environ())
    assert set(services) == set(expected), "Expected exact workspace API and worker processes"
    with SessionLocal() as db:
        assert not db.scalar(
            select(Job.id).where(Job.status.in_(["queued", "running"])).limit(1)
        ), "Wait for active jobs before taking the maintenance backup"
    run_id = uuid.uuid4().hex[:12]
    database = "graphpilot_restore_" + run_id
    backup = source_root / "backups" / (utcnow().strftime("%Y%m%dT%H%M%SZ") + "-" + run_id)
    backup.mkdir(parents=True, mode=0o700)
    restored = source_root / "restore-drills" / run_id
    restored.mkdir(parents=True, mode=0o700)
    account_id = repo_id = None
    restored_api = restored_graph = None
    stopped = []
    created_db = False
    admin = create_engine(engine.url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    email, password = f"restore-{run_id}@graphpilot.invalid", secrets.token_urlsafe(30)
    pg_bin = project / ".tools/postgres/usr/lib/postgresql/18/bin"
    pg_env = {
        **os.environ,
        "PGHOST": engine.url.host,
        "PGPORT": str(engine.url.port),
        "PGUSER": engine.url.username,
        "PGPASSWORD": engine.url.password or "",
        "LD_LIBRARY_PATH": str(project / ".tools/postgres/usr/lib/x86_64-linux-gnu"),
    }
    report = {}
    try:
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as zf:
            for path in Path("fixtures/reference").iterdir():
                if path.is_file():
                    zf.write(path, path.name)
        with httpx.Client(
            base_url="http://127.0.0.1:8000",
            headers={"Origin": "http://127.0.0.1:8000"},
            timeout=20,
        ) as client:
            response = client.post(
                "/api/auth/register",
                json={
                    "email": email,
                    "password": password,
                    "name": "Disposable restore verification",
                },
            )
            response.raise_for_status()
            account_id = response.json()["user"]["id"]
            client.headers["X-CSRF-Token"] = response.json()["csrf"]
            response = client.post(
                "/api/repositories/upload",
                files={"file": ("restore-fixture.zip", archive.getvalue(), "application/zip")},
            )
            response.raise_for_status()
            repo_id = response.json()["repository"]["id"]
            base = "/api/repositories/" + repo_id
            for _ in range(100):
                job = client.get(base + "/jobs").json()[0]
                if job["status"] in {"succeeded", "failed", "cancelled"}:
                    break
                time.sleep(0.2)
            assert job["status"] == "succeeded", job["message"]
            original = client.get(base).json()
            symbol = client.get(base + "/search?q=normalize").json()["results"][0]
            original_evidence = client.get(base + "/evidence/" + symbol["id"]).json()["content"]
        # Stop ingress before the worker so no new queue item appears mid-backup.
        for name in ["api", "worker"]:
            proc, _ = services[name]
            proc.terminate()
            stopped.append(name)
            proc.wait(timeout=15)
        with SessionLocal() as db:
            assert not db.scalar(
                select(Job.id).where(Job.status.in_(["queued", "running"])).limit(1)
            )
        dump = backup / "postgres.dump"
        dump.touch(mode=0o600)
        subprocess.run(
            [
                str(pg_bin / "pg_dump"),
                "-Fc",
                "--no-owner",
                "--no-privileges",
                "-f",
                str(dump),
                "-d",
                engine.url.database,
            ],
            env=pg_env,
            check=True,
            capture_output=True,
        )
        store.client().connection.save()
        graph_backup = backup / "falkor.rdb"
        shutil.copyfile(source_root / "falkor.rdb", graph_backup)
        graph_backup.chmod(0o600)
        artifact_backup = backup / "artifacts.tar.gz"
        artifact_backup.touch(mode=0o600)
        with tarfile.open(artifact_backup, "w:gz") as tar:
            for name in ["snapshots", "uploads", "logs"]:
                path = source_root / name
                if path.exists():
                    tar.add(path, arcname=name)
        manifest = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [dump, graph_backup, artifact_backup]
        }
        (backup / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        (backup / "manifest.json").chmod(0o600)
        with admin.connect() as connection:
            assert not connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname=:name"), {"name": database}
            )
            connection.execute(text(f'CREATE DATABASE "{database}"'))
            created_db = True
        subprocess.run(
            [
                str(pg_bin / "pg_restore"),
                "--exit-on-error",
                "--no-owner",
                "--no-privileges",
                "-d",
                database,
                str(dump),
            ],
            env=pg_env,
            check=True,
            capture_output=True,
        )
        artifact_root = restored / "artifacts"
        artifact_root.mkdir(mode=0o700)
        with tarfile.open(artifact_backup, "r:gz") as tar:
            tar.extractall(artifact_root, filter="data")
        graph_root = restored / "graph"
        graph_root.mkdir(mode=0o700)
        shutil.copyfile(graph_backup, graph_root / "falkor.rdb")
        restored_graph = FalkorDB(
            str(graph_root / "falkor.rdb"),
            serverconfig={
                "bind": "127.0.0.1",
                "port": "0",
                "appendonly": "no",
                "dir": str(graph_root),
            },
        )
        restore_url = engine.url.set(database=database).render_as_string(hide_password=False)
        restored_engine = create_engine(restore_url)
        with restored_engine.begin() as connection:
            # Native archive paths are absolute. Rebase only owned uploaded inputs;
            # source evidence itself resolves via GP_DATA_DIR on the restored API.
            rows = connection.execute(
                text("SELECT id,source FROM repositories WHERE source_type='archive'")
            ).mappings()
            for row in rows:
                original_path = Path(row["source"])
                if original_path.is_relative_to(source_root / "uploads"):
                    connection.execute(
                        text("UPDATE repositories SET source=:source WHERE id=:id"),
                        {
                            "source": str(artifact_root / original_path.relative_to(source_root)),
                            "id": row["id"],
                        },
                    )
        restored_engine.dispose()
        api_env = {
            **os.environ,
            "GP_ENVIRONMENT": "test",
            "GP_DATABASE_URL": restore_url,
            "GP_DATA_DIR": str(artifact_root),
            "GP_FALKOR_SOCKET": restored_graph.client.socket_file,
            "GP_ORIGINS": '["http://127.0.0.1:8002"]',
            "GP_COOKIE_SECURE": "false",
            "GP_LLM_BASE_URL": "",
            "GP_LLM_MODEL": "",
            "GP_LLM_API_KEY": "",
        }
        restored_api = subprocess.Popen(
            [
                python,
                str(project / ".venv/bin/uvicorn"),
                "api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8002",
                "--no-access-log",
            ],
            env=api_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        wait_ready("http://127.0.0.1:8002")
        with httpx.Client(
            base_url="http://127.0.0.1:8002",
            headers={"Origin": "http://127.0.0.1:8002"},
            timeout=10,
        ) as client:
            response = client.post("/api/auth/login", json={"email": email, "password": password})
            response.raise_for_status()
            actual = client.get(base).json()
            assert (
                actual["snapshot_id"] == original["snapshot_id"]
                and actual["stats"]["nodes"] == original["stats"]["nodes"]
            )
            graph = client.get(base + "/graph").json()
            assert any(n["id"] == symbol["id"] for n in graph["nodes"])
            evidence = client.get(base + "/evidence/" + symbol["id"]).json()
            assert evidence["content"] == original_evidence
        report = {
            "status": "passed",
            "runtime": "Native PostgreSQL/FalkorDBLite; container restore is still unverified",
            "backup_directory": str(backup.relative_to(project)),
            "writers_stopped": True,
            "isolated_database_restored": True,
            "isolated_graph_restored": True,
            "artifact_evidence_matches": True,
            "restored_login_works": True,
            "snapshot_identity_preserved": True,
            "backup_sha256": manifest,
        }
    finally:
        stop_group(restored_api)
        if restored_graph:
            try:
                restored_graph.connection.execute_command("SHUTDOWN", "NOSAVE")
            except Exception:
                pass
        if created_db:
            with admin.connect() as connection:
                connection.execute(text(f'DROP DATABASE "{database}" WITH (FORCE)'))
        admin.dispose()
        shutil.rmtree(restored, ignore_errors=True)
        for name in reversed(stopped):
            _, environment = services[name]
            log = source_root / (name + "-after-restore-drill.log")
            log.touch(mode=0o600, exist_ok=True)
            with log.open("ab") as output:
                subprocess.Popen(
                    expected[name],
                    env=environment,
                    stdout=output,
                    stderr=output,
                    start_new_session=True,
                )
        if stopped:
            wait_ready("http://127.0.0.1:8000")
        if repo_id:
            for name in store.client().list_graphs():
                if name.startswith("gp_" + repo_id.replace("-", "") + "_"):
                    store.delete_graph(name)
            shutil.rmtree(source_root / "snapshots" / repo_id, ignore_errors=True)
        with SessionLocal() as db:
            if repo_id:
                repo = db.get(Repository, repo_id)
                if repo:
                    Path(repo.source).unlink(missing_ok=True)
                    db.delete(repo)
                    db.flush()
            if account_id:
                db.execute(delete(User).where(User.id == account_id))
            db.commit()
        if report:
            report["original_api_restarted"] = True
            Path("docs/RESTORE_VERIFICATION.json").write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
