"""Broad questions and follow-ups use actual source, bounded to the caller's snapshot."""

import json

from api.graph import store
from api.models import Conversation, Membership, Repository, User
from api.worker import run_once
from tests.conftest import register
from tests.test_byok import body, chat_response, credential_key, provider_calls  # noqa: F401
from tests.test_indexing import archive_bytes


def context_repository(client):
    register(client)
    response = client.post(
        "/api/repositories/upload",
        files={
            "file": (
                "context.zip",
                archive_bytes(
                    {
                        "README.md": "# Notebook\nA note-taking app with a search page and saved notebooks.\n",
                        "package.json": '{"dependencies":{"react":"19"}}',
                        "app/main.tsx": "export const App = () => <Notes />;",
                        "app/pages/Notes.tsx": "export const Notes = () => <textarea aria-label='Note' />;",
                        "service.py": 'def save_note(text):\n    """Persist notebook content."""\n    return text.strip()\n',
                        "tests/test_notes.py": "def test_saved_note():\n    assert True\n",
                    }
                ),
                "application/zip",
            )
        },
    )
    assert response.status_code == 201
    repo_id = response.json()["repository"]["id"]
    assert run_once()
    return repo_id


def test_broad_question_collects_real_docs_and_non_python_source(
    client,
    db,
    monkeypatch,
    credential_key,  # noqa: F811
    provider_calls,  # noqa: F811
):
    repo_id = context_repository(client)
    assert client.put("/api/model", json=body()).status_code == 200
    calls, state = provider_calls
    state["handler"] = chat_response("Suggestion: improve notebook editing [E1].")
    queries = []
    original = store.query

    def counted(*args, **kwargs):
        queries.append(args[1])
        return original(*args, **kwargs)

    monkeypatch.setattr(store, "query", counted)
    result = client.post(
        f"/api/repositories/{repo_id}/context",
        json={
            "question": "can you find any new feature we can add in this app that could make user experience better"
        },
    )
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["mode"] == "ai" and len(calls) == 1
    payload = json.loads(json.loads(calls[0].content)["messages"][1]["content"])
    paths = {e["path"] for e in payload["untrusted_evidence"]}
    assert {"README.md", "app/pages/Notes.tsx", "app/main.tsx", "service.py"} <= paths
    assert any("note-taking app" in e["content"] for e in data["evidence"])
    assert any("<textarea" in e["content"] for e in data["evidence"])
    assert data["diagnostics"]["strategy"] == "repository_context"
    assert len(queries) == data["diagnostics"]["graph_queries"]
    assert data["diagnostics"]["graph_queries"] <= data["diagnostics"]["max_graph_queries"]
    assert len(data["evidence"]) <= 8
    assert sum(len(e["content"]) for e in data["evidence"]) <= 24000
    store.delete_graph(db.get(Repository, repo_id).graph_name)


def test_followups_keep_subject_and_only_send_current_users_snapshot(
    client,
    db,
    credential_key,  # noqa: F811
    provider_calls,  # noqa: F811
):
    repo_id = context_repository(client)
    assert client.put("/api/model", json=body()).status_code == 200
    calls, state = provider_calls
    state["handler"] = chat_response("The saved note is stripped [E1].")
    base = f"/api/repositories/{repo_id}/context"
    first = client.post(base, json={"question": "Find save_note"}).json()
    assert first["mode"] == "ai"
    repo = db.get(Repository, repo_id)
    owner = db.get(User, repo.owner_id)
    outsider = User(name="Other member", email="other-context@example.com", password_hash="unused")
    db.add(outsider)
    db.flush()
    db.add(Membership(repository_id=repo_id, user_id=outsider.id, permission="read"))
    for user_id, branch, snapshot, secret in [
        (outsider.id, repo.branch, first["snapshot_id"], "OTHER_USER_PRIVATE"),
        (owner.id, "another-branch", first["snapshot_id"], "OTHER_BRANCH_PRIVATE"),
        (owner.id, repo.branch, None, "OLDER_SNAPSHOT_PRIVATE"),
    ]:
        db.add(
            Conversation(
                user_id=user_id,
                repository_id=repo_id,
                branch=branch,
                snapshot_id=snapshot,
                question=secret,
                response={"answer": secret},
            )
        )
    db.commit()
    for question in ["Can you explain it more?", "What should I test for it?"]:
        result = client.post(base, json={"question": question})
        assert result.status_code == 200, result.text
        data = result.json()
        assert data["diagnostics"]["used_previous_question"]
        assert any(n["name"] == "save_note" for n in data["results"])
        assert "PRIVATE" not in calls[-1].content.decode()
    payload = json.loads(json.loads(calls[-1].content)["messages"][1]["content"])
    assert len(payload["untrusted_conversation"]) == 2
    assert payload["untrusted_conversation"][0]["question"] == "Find save_note"
    store.delete_graph(repo.graph_name)


def test_unknown_identifier_does_not_become_a_false_match(client, db):
    repo_id = context_repository(client)
    result = client.post(
        f"/api/repositories/{repo_id}/context", json={"question": "Find never_existing_symbol"}
    ).json()
    assert result["mode"] == "graph" and result["evidence"] == []
    assert result["diagnostics"]["strategy"] == "symbol_search"
    store.delete_graph(db.get(Repository, repo_id).graph_name)


def test_question_retrieval_searches_docs_without_changing_symbol_search(client, db):
    repo_id = context_repository(client)
    graph = db.get(Repository, repo_id).graph_name
    try:
        assert store.search(graph, "notebook") == []
        documented = store.search(graph, "notebook", include_docs=True)
        assert any(n["name"] == "save_note" for n in documented)
        result = client.post(
            f"/api/repositories/{repo_id}/context",
            json={"question": "Find notebook content"},
        ).json()
        assert result["diagnostics"]["strategy"] == "symbol_search"
        assert any(n["name"] == "save_note" for n in result["results"])
    finally:
        store.delete_graph(graph)
