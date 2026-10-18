"""Fixed evidence tasks on real databases; these are synthetic test facts, not demos."""

import json
from types import SimpleNamespace

from api.config import settings
from api.graph import store
from api.ingestion.python import stable_id
from api.models import Repository
from api.services.artifacts import persist_log, pytest_failure_links
from api.services.github import history_node, relation
from api.services.revisions import publish_snapshot
from tests.conftest import register
from tests.test_indexing import connected


def test_fixed_retrieval_tasks_query_accounting_and_isolation(client, db, monkeypatch):
    repo_id = connected(client)
    repo = db.get(Repository, repo_id)
    previous = repo.graph_name
    nodes, edges = store.manifest(previous)
    view = SimpleNamespace(id=repo.id, branch=repo.branch, commit_sha=repo.commit_sha)
    issue = history_node(
        view,
        "Issue",
        "7",
        name="#7 Checkout failure",
        number=7,
        body="Checkout fails for negative quantities",
        status="open",
    )
    pr = history_node(
        view,
        "PullRequest",
        "8",
        name="PR #8 Order validation",
        number=8,
        body="References #7. A fix is not established by a reference.",
        status="open",
    )
    sha = "1234567" + "a" * 33
    commit = history_node(view, "Commit", sha, name="Add order validation", sha=sha, commit=sha)
    workflow = history_node(
        view,
        "WorkflowRun",
        "9",
        name="Order checks",
        status="failure",
        sha=repo.commit_sha,
        summary="pytest failed",
    )
    saved = persist_log(
        view, "benchmark:1", "FAILED test_service.py::test_checkout - AssertionError"
    )
    log = history_node(
        view,
        "LogArtifact",
        saved["id"],
        name="CI log: order checks",
        artifact_id=saved["id"],
        commit=repo.commit_sha,
    )
    file_id = stable_id(repo.id, repo.branch, "File", "service.py")
    history = [issue, pr, commit, workflow, log]
    nodes += history
    edges += [
        relation(pr["id"], issue["id"], "REFERENCES"),
        relation(pr["id"], commit["id"], "REFERENCES"),
        relation(pr["id"], file_id, "MODIFIES"),
        relation(commit["id"], file_id, "MODIFIES"),
        relation(workflow["id"], commit["id"], "TRIGGERED_BY"),
        relation(workflow["id"], log["id"], "PRODUCES"),
    ]
    edges += pytest_failure_links(view, saved, nodes, repo.commit_sha)
    graph = store.graph_name(repo_id, repo.branch, "retrieval-benchmark")
    store.create_graph(graph, nodes, edges)
    publish_snapshot(
        db,
        repo,
        repo.branch,
        "github-sync",
        graph,
        repo.commit_sha,
        {**repo.stats, "nodes": len(nodes), "edges": len(edges)},
        {},
    )
    db.commit()
    monkeypatch.setattr(settings(), "llm_model", "")
    base = f"/api/repositories/{repo_id}"
    tasks = [
        ("Find normalize", {"normalize"}, set(), "lookup"),
        ("Find callers of normalize", {"normalize", "total", "checkout"}, {"CALLS"}, "dependency"),
        (
            "Explain dependency chain checkout normalize",
            {"checkout", "total", "normalize"},
            {"CALLS"},
            "dependency",
        ),
        (
            "Investigate issue 7",
            {issue["name"], pr["name"], commit["name"]},
            {"REFERENCES"},
            "issue",
        ),
        (
            "Identify files modified by PR 8",
            {pr["name"], "service.py"},
            {"MODIFIES"},
            "pull_request",
        ),
        (
            "Investigate failing CI",
            {workflow["name"], log["name"], "test_checkout"},
            {"PRODUCES", "RELATED_TO"},
            "ci_failure",
        ),
        ("Find commit 1234567", {commit["name"]}, {"MODIFIES"}, "lookup"),
        ("Find service.py", {"service.py"}, set(), "lookup"),
        ("UnrelatedNeverExistingSymbol", set(), set(), "lookup"),
    ]
    original_query = store.query
    observations = []
    try:
        for question, names, relations, intent in tasks:
            calls = []

            def counted_query(*args, calls=calls, **kwargs):
                calls.append(args[1])
                return original_query(*args, **kwargs)

            with monkeypatch.context() as counter:
                counter.setattr(store, "query", counted_query)
                response = client.post(base + "/context", json={"question": question})
            assert response.status_code == 200, response.text
            result = response.json()
            actual = {n["name"] for n in result["results"]}
            assert names <= actual, (question, names - actual)
            assert relations <= {e["type"] for e in result["relationships"]}, question
            assert result["diagnostics"]["intent"] == intent
            assert len(calls) == result["diagnostics"]["graph_queries"]
            assert (
                result["diagnostics"]["graph_queries"]
                <= result["diagnostics"]["max_graph_queries"]
            )
            assert result["diagnostics"]["context_bytes"] < 30000
            assert result["mode"] == "graph" and result["answer"] is None
            if not names:
                assert not result["results"] and result["warnings"]
            observations.append({"question": question, "passed": True, **result["diagnostics"]})
        # A generic number must not let an Issue query seed a PR with that number.
        assert store.search(graph, "#8", kind="Issue") == []
        assert client.get(base + "/evidence/" + commit["id"]).json()["commit"] == sha
        dashboard = client.get("/api/workspace/recent").json()
        assert len(dashboard["queries"]) == 5
        assert dashboard["failures"][0]["node"]["id"] == workflow["id"]
        assert dashboard["queries"][0]["snapshot_id"] == dashboard["failures"][0]["snapshot_id"]
        register(client, "benchmark-outsider@example.com")
        assert client.post(base + "/context", json={"question": "issue 7"}).status_code == 404
        assert client.get(base + "/conversations").status_code == 404
        assert client.get("/api/workspace/recent").json()["failures"] == []
        assert client.get("/api/workspace/recent").json()["queries"] == []
        # stdout is retained in pytest output when explicitly requested; no invented timing.
        print(json.dumps({"fixture": "recorded-shape evidence benchmark", "tasks": observations}))
    finally:
        store.delete_graph(previous)
        store.delete_graph(graph)
