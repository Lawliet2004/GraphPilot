from datetime import timedelta

import pytest
from sqlalchemy import func, select

from api.config import settings
from api.db import utcnow
from api.graph import store
from api.models import AgentToken, Job, Membership, Repository, User
from api.services.agent_tokens import issue_token, revoke_token
from tests.conftest import register
from tests.test_indexing import connected


def token_for(db, user_id):
    token, row = issue_token(db, db.get(User, user_id), "Test agent", 1)
    db.commit()
    return token, row


def rpc(client, token, method, params=None):
    headers = {
        "Accept": "application/json, text/event-stream",
        "Authorization": "Bearer " + token,
        "MCP-Protocol-Version": "2025-11-25",
    }
    return client.post(
        "/api/mcp/",
        headers=headers,
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
    )


def test_mcp_protocol_discovery_real_evidence_and_input_limits(client, db, monkeypatch):
    monkeypatch.setattr(settings(), "mcp_enabled", True)
    repo_id = connected(client)
    repo = db.get(Repository, repo_id)
    graph_name = repo.graph_name
    token, row = token_for(db, repo.owner_id)
    assert token not in row.id and row.id != token
    try:
        # Machine clients do not need a browser Origin or a cookie session.
        client.headers.pop("Origin", None)
        client.cookies.clear()
        init = rpc(
            client,
            token,
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        )
        assert init.status_code == 200, init.text
        assert init.json()["result"]["serverInfo"]["name"] == "GraphPilot"
        tools = rpc(client, token, "tools/list").json()["result"]["tools"]
        assert {t["name"] for t in tools} == {
            "list_repositories",
            "search_symbols",
            "read_evidence",
            "inspect_impact",
            "indexing_status",
        }
        assert all(t["annotations"]["readOnlyHint"] for t in tools)
        listing = rpc(client, token, "tools/call", {"name": "list_repositories", "arguments": {}})
        assert listing.status_code == 200
        assert not listing.json()["result"].get("isError"), listing.json()
        assert listing.json()["result"]["structuredContent"]["repositories"][0]["id"] == repo_id
        search = rpc(
            client,
            token,
            "tools/call",
            {
                "name": "search_symbols",
                "arguments": {"repository_id": repo_id, "query": "normalize"},
            },
        ).json()["result"]
        node_id = search["structuredContent"]["results"][0]["id"]
        source = rpc(
            client,
            token,
            "tools/call",
            {"name": "read_evidence", "arguments": {"repository_id": repo_id, "node_id": node_id}},
        ).json()["result"]
        assert "return max(0, value)" in source["structuredContent"]["content"]
        assert rpc(
            client,
            token,
            "tools/call",
            {
                "name": "search_symbols",
                "arguments": {"repository_id": repo_id, "query": "normalize", "limit": 50000},
            },
        ).json()["result"]["isError"]
        jobs_before = db.scalar(select(func.count()).select_from(Job))
        assert rpc(
            client, token, "tools/call", {"name": "run_shell", "arguments": {"command": "anything"}}
        ).json()["result"]["isError"]
        assert db.scalar(select(func.count()).select_from(Job)) == jobs_before
    finally:
        store.delete_graph(graph_name)


def test_mcp_enforces_membership_even_for_admin_and_live_revocation(client, db, monkeypatch):
    monkeypatch.setattr(settings(), "mcp_enabled", True)
    repo_id = connected(client)
    graph_name = db.get(Repository, repo_id).graph_name
    outsider = register(client, "mcp-admin@example.com")
    user = db.get(User, outsider["id"])
    user.role = "admin"
    token, row = token_for(db, user.id)
    args = {"name": "search_symbols", "arguments": {"repository_id": repo_id, "query": "normalize"}}
    try:
        denied = rpc(client, token, "tools/call", args).json()["result"]
        assert denied["isError"] and "normalize" not in str(denied.get("structuredContent", {}))
        db.add(Membership(repository_id=repo_id, user_id=user.id, permission="read"))
        db.commit()
        assert not rpc(client, token, "tools/call", args).json()["result"].get("isError", False)
        db.delete(db.get(Membership, (repo_id, user.id)))
        db.commit()
        assert rpc(client, token, "tools/call", args).json()["result"]["isError"]
        revoke_token(db, row.id)
        db.commit()
        assert rpc(client, token, "tools/list").status_code == 401
    finally:
        store.delete_graph(graph_name)


@pytest.mark.parametrize("restriction", ["expired", "disabled", "revoked"])
def test_mcp_credentials_fail_closed(client, db, monkeypatch, restriction):
    monkeypatch.setattr(settings(), "mcp_enabled", True)
    user = register(client)
    token, row = token_for(db, user["id"])
    if restriction == "expired":
        row.expires_at = utcnow() - timedelta(seconds=1)
    elif restriction == "disabled":
        db.get(User, user["id"]).disabled = True
    else:
        row.revoked_at = utcnow()
    db.commit()
    assert rpc(client, token, "tools/list").status_code == 401


def test_mcp_rejects_cookies_cross_origin_and_bad_hosts(client, db, monkeypatch):
    monkeypatch.setattr(settings(), "mcp_enabled", True)
    user = register(client)
    token, _ = token_for(db, user["id"])
    assert rpc(client, "invalid", "tools/list").status_code == 401
    assert client.post("/api/mcp/", json={}).status_code == 401
    assert (
        client.post(
            "/api/mcp/",
            headers={"Authorization": "Bearer " + token, "Origin": "https://attacker.invalid"},
            json={},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/mcp/",
            headers={
                "Authorization": "Bearer " + token,
                "Host": "attacker.invalid",
                "Accept": "application/json, text/event-stream",
            },
            json={},
        ).status_code
        == 421
    )
    # Origin exemption is limited to MCP: normal state-changing API calls still fail.
    client.headers.pop("Origin", None)
    assert client.post("/api/repositories", json={}).status_code == 403
    monkeypatch.setattr(settings(), "mcp_enabled", False)
    assert rpc(client, token, "tools/list").status_code == 404


def test_token_limits_and_user_deletion_cascade(client, db):
    user = register(client)
    token, row = token_for(db, user["id"])
    token_id = row.id
    assert len(row.id) == 64 and not row.id.startswith("gp_mcp_")
    with pytest.raises(ValueError):
        issue_token(db, db.get(User, user["id"]), "agent", 31)
    db.delete(db.get(User, user["id"]))
    db.commit()
    db.expire_all()
    assert db.get(AgentToken, token_id) is None
