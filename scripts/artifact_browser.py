"""Disposable recorded-fixture browser environment. No production seed endpoints.

Every invocation derives its own fixed-prefix test database and directory. Never
imports API modules before replacing the connection configuration.
"""

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["seed", "serve", "worker", "cleanup"])
    parser.add_argument("run_id")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-f0-9]{12}", args.run_id):
        parser.error("Test run ID must contain exactly 12 lowercase hex digits")
    config = dotenv_values(".env")
    base = make_url(os.getenv("GP_DATABASE_URL") or config["GP_DATABASE_URL"])
    database = "graphpilot_browser_" + args.run_id
    root = Path(".data/browser").resolve() / args.run_id
    os.environ.update(
        GP_DATABASE_URL=base.set(database=database).render_as_string(hide_password=False),
        GP_DATA_DIR=str(root),
        GP_ENVIRONMENT="test",
        GP_COOKIE_SECURE="false",
        GP_ORIGINS='["http://127.0.0.1:5174"]',
        GP_PUBLIC_URL="http://127.0.0.1:5174",
        GP_LLM_BASE_URL="",
        GP_LLM_MODEL="",
        GP_LLM_API_KEY="",
        GP_GITHUB_TOKEN="",
        GP_SMTP_HOST="",
        GP_SMTP_FROM="",
    )
    if args.command == "worker":
        from api.worker import main as run_worker

        sys.argv = ["graphpilot-browser-worker"]
        run_worker()
        return
    if args.command == "serve":
        import uvicorn

        uvicorn.run("api.main:app", host="127.0.0.1", port=8001, access_log=False)
        return
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        exists = connection.scalar(
            text("SELECT 1 FROM pg_database WHERE datname=:name"), {"name": database}
        )
        if args.command == "seed":
            if exists:
                raise RuntimeError("Disposable database already exists; refuse to overwrite it")
            connection.execute(text(f'CREATE DATABASE "{database}"'))
        elif not exists:
            return
    if args.command == "seed":
        subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True, stdout=sys.stderr)
        seed(json.load(sys.stdin))
    else:
        from sqlalchemy import select

        from api.db import SessionLocal, engine
        from api.graph import store
        from api.models import Repository

        with SessionLocal() as db:
            for repo in db.scalars(select(Repository)):
                prefix = "gp_" + repo.id.replace("-", "") + "_"
                for name in store.client().list_graphs():
                    if name.startswith(prefix):
                        store.delete_graph(name)
        engine.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{database}" WITH (FORCE)'))
        shutil.rmtree(root, ignore_errors=True)
    admin.dispose()


def seed(credentials):
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    from api.db import SessionLocal
    from api.main import app
    from api.models import Repository, User
    from api.services import github
    from api.services.github import GitHub
    from api.worker import run_once

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("service.py", "def checkout():\n    return 1\n")
    with TestClient(app, headers={"Origin": "http://127.0.0.1:5174"}) as client:
        response = client.post(
            "/api/auth/register", json={"name": "Automated log fixture", **credentials}
        )
        assert response.status_code == 201
        user_id = response.json()["user"]["id"]
        client.headers["X-CSRF-Token"] = response.json()["csrf"]
        response = client.post(
            "/api/repositories/upload",
            files={"file": ("fixture.zip", archive.getvalue(), "application/zip")},
        )
        assert response.status_code == 201
        repo_id = response.json()["repository"]["id"]
        run_once()
        with SessionLocal() as db:
            db.get(User, user_id).role = "admin"
            repo = db.get(Repository, repo_id)
            repo.source_type, repo.source, repo.name = (
                "github",
                "https://github.com/test/recorded-log-fixture",
                "Recorded CI log fixture",
            )
            db.commit()

        def get(self, path, params=None):
            self.requests += 1
            if path.endswith("/actions/runs"):
                return {
                    "workflow_runs": [
                        {
                            "id": 8,
                            "name": "Recorded test run",
                            "run_number": 1,
                            "run_attempt": 1,
                            "head_sha": "a" * 40,
                            "conclusion": "failure",
                            "status": "completed",
                            "html_url": "https://github.com/test/recorded-log-fixture/actions/runs/8",
                            "updated_at": "2026-01-01T00:00:00Z",
                        }
                    ]
                }, False
            if path.endswith("/actions/runs/8/jobs"):
                return {
                    "jobs": [
                        {
                            "id": 9,
                            "name": "pytest fixture",
                            "conclusion": "failure",
                            "steps": [{"name": "Run tests", "conclusion": "failure"}],
                        }
                    ]
                }, False
            return [], False

        def download(self, project, jid):
            self.log_downloads += 1
            return (
                "Synthetic automated test log\npassword=fixture-secret-never-visible\nFAILED test_checkout service.py:12\n",
                "Recorded test fixture",
            )

        original_sync = github.run_sync

        def diagnose_sync(*args):
            try:
                return original_sync(*args)
            except Exception:
                # Only synthetic fixture data is present in this disposable DB.
                import traceback

                traceback.print_exc(file=sys.stderr)
                raise

        with (
            patch.object(GitHub, "get", get),
            patch.object(GitHub, "download_log", download),
            patch.object(github, "run_sync", diagnose_sync),
        ):
            client.post(f"/api/repositories/{repo_id}/jobs?kind=github-sync")
            run_once()
        history = client.get(f"/api/repositories/{repo_id}/history?kind=LogArtifact").json()[
            "items"
        ]
        assert len(history) == 1
        print(
            json.dumps(
                {
                    "repository_id": repo_id,
                    "node_id": history[0]["id"],
                    "artifact_id": history[0]["artifact_id"],
                }
            )
        )


if __name__ == "__main__":
    main()
