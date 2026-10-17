"""Live development verification using a temporary account and a real public repo.
Creates only its own disposable verification data, then cleans it up.
"""

import json
import secrets
import shutil
import time
import uuid

import httpx
from sqlalchemy import delete

from api.config import settings
from api.db import SessionLocal
from api.graph.store import client as graph_client
from api.graph.store import delete_graph
from api.models import LoginSession, Repository, User

account_id = None
repo_id = None
started = time.perf_counter()
report = {}
try:
    with httpx.Client(
        base_url="http://127.0.0.1:8000", headers={"Origin": "http://127.0.0.1:8000"}, timeout=40
    ) as client:
        response = client.post(
            "/api/auth/register",
            json={
                "email": f"verify-{uuid.uuid4()}@graphpilot.invalid",
                "password": secrets.token_urlsafe(24),
                "name": "Disposable HTTP verification",
            },
        )
        response.raise_for_status()
        account_id = response.json()["user"]["id"]
        client.headers["X-CSRF-Token"] = response.json()["csrf"]
        response = client.post(
            "/api/repositories",
            json={
                "source_type": "github",
                "source": "https://github.com/pallets/itsdangerous",
                "branch": "main",
            },
        )
        response.raise_for_status()
        repo_id = response.json()["repository"]["id"]
        base = f"/api/repositories/{repo_id}"
        for _ in range(180):
            jobs = client.get(base + "/jobs").json()
            job = jobs[0]
            if job["status"] in {"succeeded", "failed", "cancelled"}:
                break
            time.sleep(1)
        assert job["status"] == "succeeded", job
        repo = client.get(base).json()
        results = client.get(base + "/search", params={"q": "want_bytes"}).json()["results"]
        assert results, "Known itsdangerous symbol not found"
        evidence = client.get(base + "/evidence/" + results[0]["id"]).json()
        assert "def want_bytes" in evidence["content"]
        context = client.post(
            base + "/context", json={"question": "Find callers of want_bytes"}
        ).json()
        assert context["mode"] == "graph" and context["evidence"]
        assert client.post("/api/auth/logout").status_code == 200
        assert client.get(base + "/graph").status_code == 401
        report = {
            "status": "passed",
            "repository": "https://github.com/pallets/itsdangerous",
            "commit": repo["commit_sha"],
            "files": repo["stats"]["files"],
            "functions": repo["stats"]["functions"],
            "nodes": repo["stats"]["nodes"],
            "edges": repo["stats"]["edges"],
            "duration_seconds": round(time.perf_counter() - started, 2),
            "search_symbol": "want_bytes",
            "evidence_verified": True,
            "context_mode": context["mode"],
            "protected_after_logout": True,
            "retrieval": context["diagnostics"],
        }
finally:
    if repo_id:
        for graph in graph_client().list_graphs():
            if graph.startswith("gp_" + repo_id.replace("-", "")):
                delete_graph(graph)
        shutil.rmtree(settings().data_dir.resolve() / "snapshots" / repo_id, ignore_errors=True)
    with SessionLocal() as db:
        if repo_id:
            db.execute(delete(Repository).where(Repository.id == repo_id))
        if account_id:
            db.execute(delete(LoginSession).where(LoginSession.user_id == account_id))
            db.execute(delete(User).where(User.id == account_id))
        db.commit()
    if report:
        from pathlib import Path

        Path("docs/LIVE_VERIFICATION.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
