"""Real GitHub metadata HTTP check using an owned disposable repository/account.

Unauthenticated GitHub access can defer or fail. Such observations are recorded,
not called successful. Cleanup uses the real durable owner-removal path.
"""

import json
import secrets
import time
import uuid
from collections import Counter
from pathlib import Path

import httpx
from sqlalchemy import delete, select

from api.db import SessionLocal
from api.models import Job, LoginSession, Repository, User


def main():
    report = {"repository": "https://github.com/octocat/Hello-World", "branch": "master"}
    account_id = repo_id = None
    started = time.perf_counter()
    with httpx.Client(
        base_url="http://127.0.0.1:8000", headers={"Origin": "http://127.0.0.1:8000"}, timeout=30
    ) as client:

        def wait_job(base):
            for _ in range(180):
                response = client.get(base + "/jobs")
                response.raise_for_status()
                job = response.json()[0]
                if job["status"] in {"failed", "cancelled", "succeeded"}:
                    return job
                if job["status"] == "queued" and job["attempts"] > 0:
                    return job
                time.sleep(1)
            raise RuntimeError("Verification exceeded its job observation window")

        try:
            response = client.post(
                "/api/auth/register",
                json={
                    "email": f"verify-history-{uuid.uuid4()}@graphpilot.invalid",
                    "password": secrets.token_urlsafe(24),
                    "name": "Disposable history verification",
                },
            )
            response.raise_for_status()
            account_id = response.json()["user"]["id"]
            client.headers["X-CSRF-Token"] = response.json()["csrf"]
            response = client.post(
                "/api/repositories",
                json={
                    "source_type": "github",
                    "source": report["repository"],
                    "branch": report["branch"],
                },
            )
            response.raise_for_status()
            repo_id = response.json()["repository"]["id"]
            base = f"/api/repositories/{repo_id}"
            index = wait_job(base)
            if index["status"] != "succeeded":
                report.update(status="unverified", stage="index", message=index["message"])
                return
            response = client.post(base + "/jobs?kind=github-sync")
            response.raise_for_status()
            job = wait_job(base)
            report.update(
                status="passed" if job["status"] == "succeeded" else "unverified",
                job_status=job["status"],
                message=job["message"],
            )
            if job["status"] == "succeeded":
                repo = client.get(base).json()
                history = client.get(base + "/history").json()
                report.update(
                    requests=repo["sync_state"]["requests"],
                    entity_types=dict(Counter(item["type"] for item in history["items"])),
                    published_history_entities=repo["sync_state"]["history_entities"],
                    coverage_warnings=repo["sync_state"]["warnings"],
                    pending_pr_details=len(repo["sync_state"].get("pull_details", {})),
                    log_downloads=repo["sync_state"]["log_downloads"],
                )
                assert report["entity_types"].get("Commit", 0) > 0
                assert report["entity_types"].get("PullRequest", 0) > 0
                assert report["entity_types"].get("Issue", 0) > 0
        except (httpx.HTTPError, RuntimeError, AssertionError) as exc:
            report.update(status="unverified", error_type=type(exc).__name__)
        finally:
            if repo_id:
                base = f"/api/repositories/{repo_id}"
                response = client.get(base + "/jobs")
                if response.is_success:
                    for job in response.json():
                        if job["status"] in {"queued", "running"}:
                            client.post("/api/jobs/" + job["id"] + "/cancel")
                    for _ in range(60):
                        with SessionLocal() as db:
                            active = db.scalar(
                                select(Job.id)
                                .where(
                                    Job.repository_id == repo_id,
                                    Job.status.in_(["queued", "running"]),
                                )
                                .limit(1)
                            )
                        if not active:
                            break
                        time.sleep(1)
                with SessionLocal() as db:
                    repo = db.get(Repository, repo_id)
                    name = repo.name if repo else None
                if name:
                    response = client.request("DELETE", base, json={"confirm_name": name})
                    response.raise_for_status()
                    for _ in range(60):
                        with SessionLocal() as db:
                            remaining = db.get(Repository, repo_id) is not None
                        if not remaining:
                            break
                        time.sleep(1)
                    report["disposable_repository_removed"] = not remaining
            if account_id and (not repo_id or report.get("disposable_repository_removed")):
                with SessionLocal() as db:
                    db.execute(delete(LoginSession).where(LoginSession.user_id == account_id))
                    db.execute(delete(User).where(User.id == account_id))
                    db.commit()
            report["duration_seconds"] = round(time.perf_counter() - started, 2)
            Path("docs/HISTORY_VERIFICATION.json").write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
