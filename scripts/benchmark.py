"""20-session HTTP search baseline against a real fixture index. No mocked stores."""

import concurrent.futures
import io
import json
import math
import secrets
import shutil
import statistics
import time
import uuid
import zipfile
from pathlib import Path

import httpx
import psutil
from fastapi import Request, Response
from sqlalchemy import delete

from api.auth import create_session, password_hasher
from api.config import settings
from api.db import SessionLocal
from api.graph import store
from api.models import Membership, Repository, User

BASE = "http://127.0.0.1:8000"
users = []
clients = []
repo_id = None
report = {}
try:
    # Explicit test fixture sessions, not a measurement of registration throughput.
    with SessionLocal() as db:
        hashed = password_hasher.hash(secrets.token_urlsafe(24))
        for _ in range(20):
            user = User(
                email=f"benchmark-{uuid.uuid4()}@graphpilot.invalid",
                name="Disposable benchmark session",
                password_hash=hashed,
            )
            db.add(user)
            db.flush()
            users.append(user.id)
            response = Response()
            request = Request({"type": "http", "headers": []})
            result = create_session(db, user, response, request)
            token = next(
                value.split(b";", 1)[0].split(b"=", 1)[1]
                for key, value in response.raw_headers
                if key == b"set-cookie" and value.startswith(b"gp_session=")
            )
            client = httpx.Client(
                base_url=BASE,
                headers={"Origin": BASE, "X-CSRF-Token": result["csrf"]},
                cookies={"gp_session": token.decode()},
                timeout=30,
            )
            clients.append(client)
        db.commit()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as zf:
        for path in Path("fixtures/reference").iterdir():
            if path.is_file():
                zf.write(path, path.name)
    response = clients[0].post(
        "/api/repositories/upload",
        files={"file": ("benchmark-fixture.zip", output.getvalue(), "application/zip")},
    )
    response.raise_for_status()
    repo_id = response.json()["repository"]["id"]
    with SessionLocal() as db:
        for user_id in users[1:]:
            db.add(Membership(repository_id=repo_id, user_id=user_id, permission="read"))
        db.commit()
    for _ in range(60):
        jobs = clients[0].get(f"/api/repositories/{repo_id}/jobs").json()
        job = jobs[0]
        if job["status"] in {"succeeded", "failed"}:
            break
        time.sleep(0.25)
    assert job["status"] == "succeeded", job["message"]
    proc = next(
        p
        for p in psutil.process_iter(["cmdline"])
        if p.info["cmdline"]
        and "api.main:app" in p.info["cmdline"]
        and "uv" not in Path(p.info["cmdline"][0]).name
    )
    rss_before = proc.memory_info().rss
    cpu_before = sum(proc.cpu_times()[:2])

    def search(client):
        times = []
        for _ in range(10):
            started = time.perf_counter()
            response = client.get(f"/api/repositories/{repo_id}/search", params={"q": "normalize"})
            assert (
                response.status_code == 200 and response.json()["results"][0]["name"] == "normalize"
            )
            times.append((time.perf_counter() - started) * 1000)
        return times

    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        durations = [ms for result in executor.map(search, clients) for ms in result]
    elapsed = time.perf_counter() - started
    ordered = sorted(durations)
    report = {
        "test": "real HTTP symbol search",
        "fixture": "fixtures/reference",
        "concurrent_authenticated_sessions": 20,
        "requests": len(durations),
        "successful_correct_results": len(durations),
        "elapsed_seconds": round(elapsed, 3),
        "p50_ms": round(statistics.median(durations), 2),
        "p95_ms": round(ordered[math.ceil(len(ordered) * 0.95) - 1], 2),
        "api_rss_before_mib": round(rss_before / 2**20, 2),
        "api_rss_after_mib": round(proc.memory_info().rss / 2**20, 2),
        "api_cpu_seconds": round(sum(proc.cpu_times()[:2]) - cpu_before, 3),
        "scope": "Warm native development API, real PostgreSQL and FalkorDBLite, 4-file fixture. Session fixtures seeded directly; login throughput and large-repo performance not measured.",
    }
finally:
    for client in clients:
        client.close()
    if repo_id:
        for name in store.client().list_graphs():
            if name.startswith("gp_" + repo_id.replace("-", "")):
                store.delete_graph(name)
        shutil.rmtree(settings().data_dir.resolve() / "snapshots" / repo_id, ignore_errors=True)
    with SessionLocal() as db:
        archive = (
            db.get(Repository, repo_id).source if repo_id and db.get(Repository, repo_id) else None
        )
        if repo_id:
            db.execute(delete(Repository).where(Repository.id == repo_id))
        db.execute(delete(User).where(User.id.in_(users)))
        db.commit()
        if archive:
            Path(archive).unlink(missing_ok=True)
    if report:
        Path("docs/PERFORMANCE.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
