"""Bounded synthetic-source indexing observation over real HTTP/worker/databases."""

import io
import json
import secrets
import time
import uuid
import zipfile
from pathlib import Path

import httpx
import psutil
from sqlalchemy import delete

from api.db import SessionLocal
from api.models import LoginSession, User


def main():
    worker = next(
        p
        for p in psutil.process_iter(["cmdline", "cwd"])
        if p.info["cwd"] == str(Path.cwd())
        and p.info["cmdline"]
        and Path(p.info["cmdline"][0]).name.startswith("python")
        and p.info["cmdline"][-2:] == ["-m", "api.worker"]
    )
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zf:
        for index in range(400):
            source = f"def leaf_{index:04d}():\n    return {index}\n"
            for caller in range(9):
                source += f"\ndef caller_{index:04d}_{caller}():\n    return leaf_{index:04d}()\n"
            zf.writestr(f"module_{index:04d}.py", source)
    report = {
        "fixture": "synthetic 400-file capacity observation; code never executed",
        "files": 400,
        "expected_functions": 4000,
        "expected_resolved_calls": 3600,
    }
    with httpx.Client(
        base_url="http://127.0.0.1:8000", headers={"Origin": "http://127.0.0.1:8000"}, timeout=30
    ) as client:
        response = client.post(
            "/api/auth/register",
            json={
                "email": f"capacity-{uuid.uuid4()}@graphpilot.invalid",
                "password": secrets.token_urlsafe(24),
                "name": "Disposable capacity fixture",
            },
        )
        response.raise_for_status()
        account = response.json()["user"]["id"]
        client.headers["X-CSRF-Token"] = response.json()["csrf"]
        cpu_before, rss_before = sum(worker.cpu_times()[:2]), worker.memory_info().rss
        peak = rss_before
        started = time.perf_counter()
        response = client.post(
            "/api/repositories/upload",
            files={"file": ("capacity-fixture.zip", archive.getvalue(), "application/zip")},
        )
        response.raise_for_status()
        repo_id = response.json()["repository"]["id"]
        base = f"/api/repositories/{repo_id}"
        for _ in range(1200):
            peak = max(peak, worker.memory_info().rss)
            job = client.get(base + "/jobs").json()[0]
            if job["status"] in {"succeeded", "failed", "cancelled"}:
                break
            time.sleep(0.1)
        assert job["status"] == "succeeded", job["message"]
        repo = client.get(base).json()
        stats = repo["stats"]
        assert (
            stats["files"] == 400 and stats["functions"] == 4000 and stats["resolved_calls"] == 3600
        )
        graph = client.get(base + "/graph").json()
        assert len(graph["nodes"]) == 80 and graph["bounded"]
        leaf = client.get(base + "/search?q=leaf_0399").json()["results"][0]
        assert leaf["path"] == "module_0399.py"
        assert "return 399" in client.get(base + "/evidence/" + leaf["id"]).json()["content"]
        report.update(
            status="passed",
            duration_seconds=round(time.perf_counter() - started, 2),
            nodes=stats["nodes"],
            edges=stats["edges"],
            initial_graph_nodes=len(graph["nodes"]),
            worker_cpu_seconds=round(sum(worker.cpu_times()[:2]) - cpu_before, 2),
            worker_rss_before_mib=round(rss_before / 1048576, 2),
            worker_rss_sampled_peak_mib=round(peak / 1048576, 2),
            scope="Native fixture index. RSS sampled every ~100ms; worker CPU excludes separate FalkorDB process. Not a maximum-size or production SLA.",
        )
        # Use real deletion so graph/source/input cleanup is part of this observation.
        assert (
            client.request("DELETE", base, json={"confirm_name": "capacity-fixture"}).status_code
            == 202
        )
        with SessionLocal() as db:
            from api.models import Repository

            for _ in range(100):
                db.expire_all()
                if db.get(Repository, repo_id) is None:
                    break
                time.sleep(0.1)
            assert db.get(Repository, repo_id) is None
            db.execute(delete(LoginSession).where(LoginSession.user_id == account))
            db.execute(delete(User).where(User.id == account))
            db.commit()
        report["owned_data_removed"] = True
    Path("docs/CAPACITY_VERIFICATION.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
