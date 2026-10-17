import io
import subprocess
import zipfile

import pytest
from sqlalchemy import select

from api.config import settings
from api.graph import store
from api.ingestion.python import build_graph, parse_file, stable_id
from api.ingestion.sources import SourceError, extract_zip, github_url
from api.models import Job, Repository
from api.worker import run_once
from tests.conftest import register


def archive_bytes(files=None):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as zf:
        if files:
            for path, content in files.items():
                zf.writestr(path, content)
        else:
            from pathlib import Path

            for path in Path("fixtures/reference").iterdir():
                if path.is_file():
                    zf.write(path, path.name)
    return output.getvalue()


def connected(client):
    register(client)
    response = client.post(
        "/api/repositories/upload",
        files={"file": ("reference.zip", archive_bytes(), "application/zip")},
    )
    assert response.status_code == 201, response.text
    repo_id = response.json()["repository"]["id"]
    assert run_once()
    jobs = client.get(f"/api/repositories/{repo_id}/jobs").json()
    assert jobs[0]["status"] == "succeeded", jobs
    return repo_id


def test_real_graph_ingestion_search_evidence_and_unchanged_scan(client, db):
    repo_id = connected(client)
    base = f"/api/repositories/{repo_id}"
    repo = client.get(base).json()
    assert repo["stats"]["files"] == 4
    assert repo["stats"]["functions"] == 5
    assert repo["stats"]["resolved_calls"] == 4
    result = client.get(base + "/search", params={"q": "normalize"}).json()["results"]
    assert len(result) == 1 and result[0]["score"] == 1
    node_id = result[0]["id"]
    neighbors = client.get(
        base + f"/nodes/{node_id}/neighbors", params={"relation": "CALLS"}
    ).json()
    assert any(n["name"] == "total" for n in neighbors["nodes"])
    evidence = client.get(base + f"/evidence/{node_id}").json()
    assert "return max(0, value)" in evidence["content"]
    assert evidence["start_line"] <= 3 and evidence["commit"] == repo["commit_sha"]
    impact = client.get(base + f"/impact/{node_id}").json()
    assert any(r["node"]["name"] == "checkout" and r["distance"] == 2 for r in impact["results"])
    calls_only = client.get(base + "/graph?relation=CALLS").json()
    assert calls_only["edges"] and all(e["type"] == "CALLS" for e in calls_only["edges"])
    assert client.get(base + "/graph?relation=DROP_GRAPH").status_code == 422
    graph = client.get(base + "/graph").json()
    assert len(graph["nodes"]) == repo["stats"]["nodes"]
    assert all(
        e["source"] in {n["id"] for n in graph["nodes"]}
        and e["target"] in {n["id"] for n in graph["nodes"]}
        for e in graph["edges"]
    )
    assert (
        client.get(base + "/search", params={"q": "' MATCH (n) DETACH DELETE n //"}).json()[
            "results"
        ]
        == []
    )
    assert client.get(base + "/graph", params={"limit": 99999}).status_code == 422
    previous_graph = db.get(Repository, repo_id).graph_name
    assert client.post(base + "/jobs").status_code == 201
    run_once()
    stats = client.get(base).json()["stats"]
    assert stats["parsed_files"] == 0 and stats["skipped_files"] == 4 and stats["graph_writes"] == 0
    db.expire_all()
    assert db.get(Repository, repo_id).graph_name == previous_graph
    store.delete_graph(previous_graph)


def test_repository_and_node_isolation(client, db):
    repo_id = connected(client)
    base = f"/api/repositories/{repo_id}"
    node_id = client.get(base + "/search", params={"q": "normalize"}).json()["results"][0]["id"]
    graph_name = db.get(Repository, repo_id).graph_name
    register(client, "outsider@example.com")
    for path in [
        base,
        base + "/graph",
        base + "/search?q=normalize",
        base + f"/evidence/{node_id}",
        base + f"/nodes/{node_id}/neighbors",
        base + f"/impact/{node_id}",
        base + "/jobs",
    ]:
        assert client.get(path).status_code == 404, path
    assert client.post(base + "/jobs").status_code == 404
    assert client.get("/api/repositories").json() == []
    store.delete_graph(graph_name)


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/a/b",
        "https://github.com.evil.org/a/b",
        "https://github.com/a/b?x=y",
        "https://user:pass@github.com/a/b",
        "file:///etc/passwd",
        "https://127.0.0.1/a/b",
        "https://github.com/a/../b",
        "https://github.com/a/b/tree/main",
    ],
)
def test_reject_untrusted_urls(url):
    with pytest.raises((SourceError, ValueError)):
        github_url(url)


def test_zip_traversal_and_symlink_rejected(tmp_path):
    for filename in ["../escape.py", "/etc/escape.py", "a/../../escape.py", "a\\escape.py"]:
        path = tmp_path / "bad.zip"
        path.write_bytes(archive_bytes({filename: "bad"}))
        with pytest.raises(SourceError):
            extract_zip(path, tmp_path / "out")
    path = tmp_path / "sym.zip"
    with zipfile.ZipFile(path, "w") as zf:
        info = zipfile.ZipInfo("link")
        info.external_attr = 0o120777 << 16
        zf.writestr(info, "/etc/passwd")
    with pytest.raises(SourceError):
        extract_zip(path, tmp_path / "out")
    assert not (tmp_path / "escape.py").exists()


def test_static_resolution_does_not_guess_and_ids_are_scoped():
    files = {}
    for path, source in {
        "a.py": "def same(): pass\ndef f():\n    same()\n    dynamic.run()\n",
        "b.py": "def same(): pass",
    }.items():
        files[path] = {"hash": "x", "lines": 4, "parsed": parse_file(path, source)}
    nodes, edges, stats = build_graph("repo", "main", "abc", "fixture", files)
    calls = [e for e in edges if e["type"] == "CALLS"]
    target = next(n for n in nodes if n["id"] == calls[0]["target"])
    assert target["path"] == "a.py" and stats["unresolved_calls"] == 1
    assert stable_id("repo", "main", "File", "a.py") != stable_id("repo", "dev", "File", "a.py")
    assert stable_id("repo", "main", "File", "a.py") != stable_id("other", "main", "File", "a.py")


def test_local_incremental_update_deleted_edges_and_history(client, db, tmp_path):
    source = tmp_path / "gitrepo"
    source.mkdir()

    def git(*args):
        subprocess.run(["git", "-C", str(source), *args], check=True, capture_output=True)

    git("init", "-b", "main")
    git("config", "user.name", "Fixture")
    git("config", "user.email", "fixture@example.com")
    (source / "a.py").write_text(
        "def helper():\n    return 1\n\ndef caller():\n    return helper()\n"
    )
    (source / "b.py").write_text("def untouched():\n    return 2\n")
    git("add", ".")
    git("commit", "-m", "Initial fixture")
    settings().allowed_local_roots = [tmp_path]
    register(client)
    response = client.post(
        "/api/repositories", json={"source_type": "local", "source": str(source)}
    )
    assert response.status_code == 201, response.text
    repo_id = response.json()["repository"]["id"]
    assert run_once()
    db.expire_all()
    repo = db.get(Repository, repo_id)
    old_graph = repo.graph_name
    assert repo.status == "ready", client.get(f"/api/repositories/{repo_id}/jobs").json()
    (source / "a.py").write_text("def helper_new():\n    return 3\n\ndef caller():\n    return 5\n")
    git("add", ".")
    git("commit", "-m", "Rename helper and remove call")
    base = f"/api/repositories/{repo_id}"
    assert client.post(base + "/jobs").status_code == 201
    assert run_once()
    db.expire_all()
    repo = db.get(Repository, repo_id)
    assert repo.stats["parsed_files"] == 1 and repo.stats["skipped_files"] == 1
    assert repo.stats["delta"]["edges_deleted"] >= 1
    assert client.get(base + "/search?q=helper_new").json()["results"]
    assert store.search(old_graph, "helper")[0]["name"] == "helper"
    assert store.query(repo.graph_name, "MATCH ()-[r:CALLS]->() RETURN count(r)")[0][0] == 0
    assert client.post(base + "/jobs").status_code == 201
    run_once()
    assert client.get(base).json()["stats"]["graph_writes"] == 0
    for g in store.client().list_graphs():
        if g.startswith("gp_" + repo_id.replace("-", "")):
            store.delete_graph(g)
    settings().allowed_local_roots = []


def test_job_claim_serialization_and_cancellation(client, db):
    register(client)
    response = client.post(
        "/api/repositories/upload",
        files={"file": ("source.zip", archive_bytes(), "application/zip")},
    )
    data = response.json()
    assert client.post("/api/repositories/" + data["repository"]["id"] + "/jobs").status_code == 409
    assert client.post("/api/jobs/" + data["job"]["id"] + "/cancel").status_code == 200
    assert not run_once()
    assert db.scalar(select(Job)).status == "cancelled"


def test_source_link_encodes_git_filename_query_and_fragment_characters(client, db):
    register(client)
    response = client.post(
        "/api/repositories/upload",
        files={
            "file": (
                "special.zip",
                archive_bytes({"weird ?#.py": "def special_symbol(): return 1\n"}),
                "application/zip",
            )
        },
    )
    assert response.status_code == 201
    repo_id = response.json()["repository"]["id"]
    assert run_once()
    repo = db.get(Repository, repo_id)
    repo.source_type, repo.source = "github", "https://github.com/test/source-link-fixture"
    db.commit()
    base = f"/api/repositories/{repo_id}"
    node = client.get(base + "/search?q=special_symbol").json()["results"][0]
    try:
        evidence = client.get(base + "/evidence/" + node["id"]).json()
        assert evidence["url"].endswith("/weird%20%3F%23.py#L1")
        assert "def special_symbol" in evidence["content"]
    finally:
        store.delete_graph(repo.graph_name)


def test_overloads_redefinitions_and_shadowing_do_not_fabricate_calls():
    source = """
def helper(): return 1

def shadowed(helper):
    return helper()

def overwritten():
    helper = lambda: 2
    return helper()

class Thing:
    @property
    def value(self): return helper()
    @value.setter
    def value(self, new): pass
    def sibling(self): return 1
    def method(self): return sibling()
"""
    parsed = parse_file("sample.py", source)
    nodes, edges, stats = build_graph(
        "r", "main", "sha", "fixture", {"sample.py": {"hash": "h", "lines": 20, "parsed": parsed}}
    )
    assert len({n["id"] for n in nodes}) == len(nodes)
    names = {n["id"]: n.get("qualified_name", n["name"]) for n in nodes}
    calls = [e for e in edges if e["type"] == "CALLS"]
    assert [(names[e["source"]], names[e["target"]]) for e in calls] == [
        ("Thing.value@1", "helper")
    ]
    assert stats["unresolved_calls"] == 3


def test_git_file_rename_delete_interrupted_publication_and_retry(
    client, db, tmp_path, monkeypatch
):
    from api.services import indexing

    source = tmp_path / "rename-fixture"
    source.mkdir()

    def git(*args):
        subprocess.run(["git", "-C", str(source), *args], check=True, capture_output=True)

    git("init", "-b", "main")
    git("config", "user.name", "Rename fixture")
    git("config", "user.email", "fixture@example.com")
    (source / "a.py").write_text("def helper(): return 1\ndef caller(): return helper()\n")
    (source / "b.py").write_text("def removed(): return 2\n")
    git("add", ".")
    git("commit", "-m", "Initial source")
    monkeypatch.setattr(settings(), "allowed_local_roots", [tmp_path])
    register(client)
    response = client.post(
        "/api/repositories", json={"source_type": "local", "source": str(source)}
    )
    assert response.status_code == 201
    repo_id = response.json()["repository"]["id"]
    base = f"/api/repositories/{repo_id}"
    assert run_once()
    db.expire_all()
    previous = db.get(Repository, repo_id).graph_name
    snapshots = settings().data_dir.resolve() / "snapshots" / repo_id
    before = set(snapshots.iterdir())
    git("mv", "a.py", "renamed.py")
    git("rm", "b.py")
    git("commit", "-m", "Rename and delete files")
    original_checkpoint = indexing.checkpoint

    def interrupted(job_id, worker_id, progress, message):
        if progress == 95:
            raise SourceError("Synthetic interruption before publication")
        return original_checkpoint(job_id, worker_id, progress, message)

    try:
        with monkeypatch.context() as interruption:
            interruption.setattr(indexing, "checkpoint", interrupted)
            client.post(base + "/jobs")
            assert run_once()
        assert client.get(base + "/jobs").json()[0]["status"] == "failed"
        assert client.get(base).json()["stats"]["files"] == 2
        assert set(snapshots.iterdir()) == before
        assert [
            n
            for n in store.client().list_graphs()
            if n.startswith("gp_" + repo_id.replace("-", "") + "_")
        ] == [previous]
        client.post(base + "/jobs")
        assert run_once()
        repo = client.get(base).json()
        assert repo["stats"]["files"] == 1 and repo["stats"]["deleted_files"] == 2
        assert repo["stats"]["parsed_files"] == 1 and repo["stats"]["resolved_calls"] == 1
        assert client.get(base + "/search?q=removed").json()["results"] == []
        assert client.get(base + "/search?q=helper").json()["results"][0]["path"] == "renamed.py"
        assert store.search(previous, "a.py", kind="File")
    finally:
        for name in store.client().list_graphs():
            if name.startswith("gp_" + repo_id.replace("-", "") + "_"):
                store.delete_graph(name)


def test_lost_publication_acknowledgement_does_not_delete_committed_graph_or_source(
    client, db, monkeypatch
):
    from pathlib import Path

    from sqlalchemy.orm import Session

    repo_id = connected(client)
    repo = db.get(Repository, repo_id)
    previous = repo.graph_name
    Path(repo.source).write_bytes(
        archive_bytes({"fresh.py": "def next_symbol():\n    return 42\n"})
    )
    original_commit = Session.commit
    lost = [False]

    def commit_then_lose_ack(session):
        publishing = not lost[0] and any(
            isinstance(obj, Job) and obj.repository_id == repo_id and obj.status == "succeeded"
            for obj in session.identity_map.values()
        )
        original_commit(session)
        if publishing:
            lost[0] = True
            raise RuntimeError("Synthetic lost commit acknowledgement")

    base = f"/api/repositories/{repo_id}"
    try:
        client.post(base + "/jobs")
        with monkeypatch.context() as unknown_commit:
            unknown_commit.setattr(Session, "commit", commit_then_lose_ack)
            assert run_once()
        assert lost[0]
        repo = client.get(base).json()
        assert client.get(base + "/jobs").json()[0]["status"] == "succeeded"
        assert repo["stats"]["files"] == 1
        node = client.get(base + "/search?q=next_symbol").json()["results"][0]
        assert "return 42" in client.get(base + "/evidence/" + node["id"]).json()["content"]
        assert previous in store.client().list_graphs()
    finally:
        for name in store.client().list_graphs():
            if name.startswith("gp_" + repo_id.replace("-", "") + "_"):
                store.delete_graph(name)
