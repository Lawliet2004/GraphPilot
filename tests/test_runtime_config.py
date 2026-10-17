import json
import subprocess
from datetime import timedelta

from sqlalchemy import select

from api.db import utcnow
from api.graph import store
from api.models import Audit, LogArtifact, Repository, RuntimeSetting, User
from api.services.artifacts import persist_log
from api.services.github import GitHub
from api.services.runtime_config import log_policy
from tests.test_indexing import connected


def test_durable_admin_log_policy_limits_and_retention(client, db):
    repo_id = connected(client)
    path = "/api/admin/config"
    policy = {"max_log_downloads": 0, "max_log_bytes": 1000, "artifact_retention_days": 1}
    assert client.get(path).status_code == 403
    assert client.put(path, json=policy).status_code == 403
    repo = db.get(Repository, repo_id)
    before = persist_log(repo, "before-policy", "A retained test log")
    before_expiry = db.get(LogArtifact, before["id"]).expires_at
    db.get(User, repo.owner_id).role = "admin"
    db.commit()
    response = client.put(path, json=policy)
    assert response.status_code == 200 and response.json()["values"] == policy
    assert client.get(path).json()["values"] == policy and log_policy() == policy
    assert len(list(db.scalars(select(RuntimeSetting)))) == 3
    assert db.scalar(select(Audit).where(Audit.action == "admin.configuration_updated"))
    result = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "-c",
            "import json; from api.services.runtime_config import log_policy; print(json.dumps(log_policy()))",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout) == policy
    after = persist_log(repo, "after-policy", "Another retained test log")
    row = db.get(LogArtifact, after["id"])
    assert utcnow() + timedelta(hours=23) < row.expires_at < utcnow() + timedelta(hours=25)
    db.expire_all()
    assert db.get(LogArtifact, before["id"]).expires_at == before_expiry
    api = GitHub()
    content, status = api.download_log("test/reference", 123)
    assert content is None and "budget" in status and api.requests == 0
    api.client.close()
    for invalid in [
        policy | {"max_log_downloads": -1},
        policy | {"max_log_bytes": 10_000_001},
        policy | {"artifact_retention_days": 0},
        policy | {"max_log_downloads": True},
        policy | {"database_url": "cannot-change-provider-config"},
    ]:
        assert client.put(path, json=invalid).status_code == 422
    assert client.get(path).json()["values"] == policy
    db.get(User, repo.owner_id).role = "user"
    db.commit()
    assert client.put(path, json=policy).status_code == 403
    store.delete_graph(repo.graph_name)
