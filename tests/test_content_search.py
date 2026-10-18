"""Contracts for the bounded literal scanner and exact source ranges.

Reproduces the handoff acceptance fixtures: the four baseline misses
(X-CSRF-Token, "Request origin is not allowed", python-ast-3, graph_queries),
short/punctuation/Unicode literals, a match beyond line 200, a late match in a
very long line, CRLF and U+2028 semantics, incomplete manifest/source states,
cap disclosure, snapshot pinning, access control and MCP parity.
"""

import dataclasses
import hashlib
import io
import subprocess
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.config import settings
from api.db import utcnow
from api.graph import store
from api.ingestion.python import parse_file
from api.ingestion.sources import SourceError
from api.models import Membership, Repository, Snapshot, User
from api.services import source_search
from api.services.agent_tokens import issue_token
from api.services.revisions import view_repository
from api.services.source_ranges import read_snapshot_bytes, snapshot_root
from api.worker import run_once
from tests.conftest import register
from tests.test_mcp import rpc, token_for


def zip_bytes(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as zf:
        for path, content in files.items():
            zf.writestr(path, content)
    return output.getvalue()


def upload_repo(client, files, filename="sources.zip"):
    response = client.post(
        "/api/repositories/upload",
        files={"file": (filename, zip_bytes(files), "application/zip")},
    )
    assert response.status_code == 201, response.text
    repo_id = response.json()["repository"]["id"]
    assert run_once()
    jobs = client.get(f"/api/repositories/{repo_id}/jobs").json()
    assert jobs[0]["status"] == "succeeded", jobs
    return repo_id


def indexed(client, files):
    register(client)
    return upload_repo(client, files)


DEEP = "".join(f"# padding {i}\n" for i in range(1, 231)) + (
    'def marker_target():\n'
    '    headers = {"X-CSRF-Token": "*"}\n'
    '    message = "Request origin is not allowed"\n'
    '    parser = "python-ast-3"\n'
    '    diagnostic = "graph_queries"\n'
    "    return headers, message, parser, diagnostic\n"
)
LONG_LINE = 'row = "' + "x" * 400 + "NEEDLE_LATE" + "y" * 300 + '"\n'
FILES = {
    "src/deep.py": DEEP,
    "src/longline.py": LONG_LINE + 'tail = "end"\n',
    "src/crlf.py": 'first = "one"\r\nsecond = "two"\r\nMARKER_CRLF = 3\r\n',
    "src/unisep.py": 'a = 1\u2028still = "one logical line"\nMARKER_SEP = 2\n',
    "src/short.py": (
        'one = "a"\n'
        'two = "ab"\n'
        'rx = "a.*b"  # regex-shaped literal\n'
        'quote = "it\'s" + \'"ok"\'\n'
        'tick = "`pre`"\n'
        'uni = "λ → Ω"\n'
        'pad = "  spaced  "\n'
    ),
    "docs/notes.txt": "plain text is scanned too — X-CSRF-Token appears here\n",
}


def find_file(client, base, path):
    hits = client.get(base + "/search", params={"q": path}).json()["results"]
    return next(n for n in hits if n.get("path") == path)


def test_baseline_literals_and_exact_matching(client):
    repo_id = indexed(client, FILES)
    base = f"/api/repositories/{repo_id}"
    for literal in (
        "X-CSRF-Token",
        "Request origin is not allowed",
        "python-ast-3",
        "graph_queries",
    ):
        body = client.get(base + "/search/content", params={"q": literal}).json()
        assert body["results"], literal
        assert all(literal in h["snippet"] for h in body["results"])
        assert body["truncated"] is False
        assert body["completion_reason"] == "exhausted"
        assert body["total"] == len(body["results"])
        assert body["scope"]["snapshot_id"]
    # deep.py and notes.txt both carry the CSRF literal.
    hits = client.get(base + "/search/content", params={"q": "X-CSRF-Token"}).json()
    assert {h["path"] for h in hits["results"]} == {"src/deep.py", "docs/notes.txt"}
    # One/two-character, punctuation, quotes, backticks, Unicode, padding.
    for literal, count in (
        ('"a"', 1),
        ('"ab"', 1),
        ('"`pre`"', 1),
        ("λ → Ω", 1),
        ('"  spaced  "', 1),
    ):
        body = client.get(
            base + "/search/content", params={"q": literal, "case": "true"}
        ).json()
        assert len(body["results"]) == count, literal
    # Regex characters are matched literally, never interpreted.
    body = client.get(base + "/search/content", params={"q": "a.*b"}).json()
    assert len(body["results"]) == 1 and body["results"][0]["path"] == "src/short.py"
    body = client.get(base + "/search/content", params={"q": "a.*X"}).json()
    assert body["results"] == []
    # Leading/trailing spaces inside the literal are preserved, not stripped.
    spaced = client.get(
        base + "/search/content", params={"q": "  spaced  ", "case": "true"}
    ).json()
    assert len(spaced["results"]) == 1
    # Input limits are typed and enforced.
    assert client.get(base + "/search/content", params={"q": ""}).status_code == 422
    assert (
        client.get(base + "/search/content", params={"q": "x" * 201}).status_code
        == 422
    )
    assert (
        client.get(base + "/search/content", params={"q": "x", "limit": 51}).status_code
        == 422
    )


def test_case_behavior_and_filters(client):
    repo_id = indexed(client, FILES)
    base = f"/api/repositories/{repo_id}"
    insensitive = client.get(
        base + "/search/content", params={"q": "x-csrf-token"}
    ).json()
    assert len(insensitive["results"]) == 2
    sensitive = client.get(
        base + "/search/content", params={"q": "x-csrf-token", "case": "true"}
    ).json()
    assert sensitive["results"] == []
    scoped_path = client.get(
        base + "/search/content",
        params={"q": "X-CSRF-Token", "path": "docs"},
    ).json()
    assert {h["path"] for h in scoped_path["results"]} == {"docs/notes.txt"}
    only_py = client.get(
        base + "/search/content",
        params={"q": "X-CSRF-Token", "suffix": ".py"},
    ).json()
    assert {h["path"] for h in only_py["results"]} == {"src/deep.py"}
    # Traversal-shaped filters are rejected.
    assert (
        client.get(
            base + "/search/content", params={"q": "x", "path": "../etc"}
        ).status_code
        == 422
    )
    assert (
        client.get(
            base + "/search/content", params={"q": "x", "suffix": "../x"}
        ).status_code
        == 422
    )


def test_match_after_line_200_opens_and_asks_that_range(client):
    repo_id = indexed(client, FILES)
    base = f"/api/repositories/{repo_id}"
    hits = client.get(base + "/search/content", params={"q": "graph_queries"}).json()
    hit = hits["results"][0]
    assert hit["line"] == 235 and hit["path"] == "src/deep.py"
    evidence = client.get(
        base + f"/evidence/{hit['node_id']}", params={"around": hit["line"]}
    ).json()
    assert evidence["start_line"] == 232 and evidence["end_line"] >= 235
    assert "graph_queries" in evidence["content"]
    # The same selected range feeds Ask via a pinned source selection.
    answer = client.post(
        base + "/context",
        json={
            "question": "Explain this diagnostic",
            "source": {"node_id": hit["node_id"], "around": hit["line"]},
        },
    ).json()
    pinned = next(c for c in answer["evidence"] if c.get("pinned"))
    assert pinned["start_line"] <= hit["line"] <= pinned["end_line"]
    assert "graph_queries" in pinned["content"]
    # A quoted literal in the question recovers the same file and match line.
    quoted = client.post(
        base + "/context", json={"question": 'Where is "X-CSRF-Token" set?'}
    ).json()
    matched = [
        c
        for c in quoted["evidence"]
        if c.get("match") and c["match"]["line"] == 232 and c["path"] == "src/deep.py"
    ]
    assert matched and "X-CSRF-Token" in matched[0]["content"]
    assert matched[0]["start_line"] <= 232 <= matched[0]["end_line"]


def test_late_long_line_match_is_bounded_and_anchored(client):
    repo_id = indexed(client, FILES)
    base = f"/api/repositories/{repo_id}"
    hits = client.get(base + "/search/content", params={"q": "NEEDLE_LATE"}).json()
    hit = hits["results"][0]
    assert hit["column"] > 400
    # The snippet is a bounded window around the match, with both cut flags.
    assert hit["snippet_start_partial"] and hit["snippet_end_partial"]
    assert "NEEDLE_LATE" in hit["snippet"] and len(hit["snippet"]) < 200
    assert hit["line_length"] > 500
    # Opening the hit serves the real line, not a silently capped beginning.
    evidence = client.get(
        base + f"/evidence/{hit['node_id']}", params={"around": 1}
    ).json()
    assert "NEEDLE_LATE" in evidence["content"]
    assert evidence["end_line_partial"] is False


def test_crlf_and_u2028_line_semantics(client):
    repo_id = indexed(client, FILES)
    base = f"/api/repositories/{repo_id}"
    crlf = client.get(base + "/search/content", params={"q": "MARKER_CRLF"}).json()
    assert crlf["results"][0]["line"] == 3  # \r\n is one line break
    unisep = client.get(base + "/search/content", params={"q": "MARKER_SEP"}).json()
    assert unisep["results"][0]["line"] == 2  # U+2028 does not create a line
    node = find_file(client, base, "src/crlf.py")
    evidence = client.get(
        base + f"/evidence/{node['id']}", params={"start": 1, "end": 3}
    ).json()
    assert "\r\n" in evidence["content"]  # original bytes preserved


def test_missing_hash_mismatch_and_symlink_are_incomplete(client):
    repo_id = indexed(client, FILES)
    base = f"/api/repositories/{repo_id}"
    stats = client.get(base).json()["stats"]
    root = settings().data_dir / "snapshots" / repo_id / stats["tree_hash"]
    # A hash-corrupted retained file is skipped, not silently read.
    (root / "src/deep.py").write_text('corrupted = "X-CSRF-Token"\n')
    body = client.get(base + "/search/content", params={"q": "X-CSRF-Token"}).json()
    assert body["truncated"] and body["total"] is None
    assert body["scan"]["skip_reasons"]["hash_mismatch"] == 1
    assert {h["path"] for h in body["results"]} == {"docs/notes.txt"}
    # A deleted retained file cannot masquerade as a clean zero-result scan.
    (root / "src/short.py").unlink()
    body = client.get(base + "/search/content", params={"q": "λ → Ω"}).json()
    assert body["results"] == []
    assert body["truncated"] and body["scan"]["skip_reasons"]["unavailable"] == 1
    # A symlinked member is never followed even when it exists in the manifest.
    (root / "docs/notes.txt").unlink()
    (root / "docs/notes.txt").symlink_to(root / "src/longline.py")
    body = client.get(base + "/search/content", params={"q": "NEEDLE_LATE"}).json()
    assert {h["path"] for h in body["results"]} == {"src/longline.py"}
    assert body["scan"]["skip_reasons"]["unavailable"] >= 1


def test_manifest_count_mismatch_is_incomplete(client, db):
    repo_id = indexed(client, FILES)
    owner = db.get(
        User, db.get(Repository, repo_id).owner_id
    )
    view = view_repository(db, owner, repo_id)
    wrong = dataclasses.replace(view, stats={**view.stats, "files": 999})
    result = source_search.search_source(wrong, "X-CSRF-Token")
    assert result["truncated"] and result["scan"]["manifest_incomplete"]
    assert result["total"] is None


def test_caps_disclose_incomplete_scans(client, monkeypatch):
    repo_id = indexed(client, FILES)
    base = f"/api/repositories/{repo_id}"
    monkeypatch.setattr(source_search, "MATCH_LIMIT", 2)
    body = client.get(base + "/search/content", params={"q": "padding"}).json()
    assert body["truncated"] and body["completion_reason"] == "matches_cap"
    assert body["total"] is None and body["has_more"]
    monkeypatch.setattr(source_search, "MATCH_LIMIT", 200)
    monkeypatch.setattr(source_search, "TIME_BUDGET_MS", 0)
    body = client.get(base + "/search/content", params={"q": "zzz-nothing"}).json()
    assert body["completion_reason"] == "time_budget" and body["truncated"]
    assert body["results"] == [] and body["total"] is None  # no fake exhaustive zero


def test_deterministic_order_and_query_count(client, monkeypatch):
    repo_id = indexed(client, FILES)
    base = f"/api/repositories/{repo_id}"
    calls = []
    real_query = store.query

    def counted(graph, statement, params=None, **kwargs):
        calls.append(statement)
        return real_query(graph, statement, params, **kwargs)

    monkeypatch.setattr(store, "query", counted)
    first = client.get(base + "/search/content", params={"q": "padding"}).json()
    second = client.get(base + "/search/content", params={"q": "padding"}).json()
    monkeypatch.undo()
    assert [h["path"] for h in first["results"]] == [
        h["path"] for h in second["results"]
    ]
    assert first["graph_queries"] == 1 == second["graph_queries"]
    assert len(calls) == 2  # one manifest query per scan


def test_snapshot_pinning_and_retention(client, db, tmp_path, monkeypatch):
    source = tmp_path / "srcrepo"
    source.mkdir()

    def git(*args):
        subprocess.run(["git", "-C", str(source), *args], check=True, capture_output=True)

    git("init", "-b", "main")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test")
    (source / "deep.py").write_text(DEEP)
    git("add", ".")
    git("commit", "-m", "v1")
    monkeypatch.setattr(settings(), "allowed_local_roots", [tmp_path])
    register(client)
    response = client.post(
        "/api/repositories", json={"source_type": "local", "source": str(source)}
    )
    assert response.status_code == 201, response.text
    repo_id = response.json()["repository"]["id"]
    assert run_once()
    base = f"/api/repositories/{repo_id}"
    initial = client.get(base).json()
    old = {"revision": initial["snapshot_id"]}
    first = client.get(
        base + "/search/content", params=old | {"q": "python-ast-3"}
    ).json()
    assert first["results"] and first["scope"]["snapshot_id"] == old["revision"]
    # Reindex with changed source: head moves, the pinned snapshot stays stable.
    (source / "deep.py").write_text(DEEP.replace("python-ast-3", "python-ast-4"))
    git("add", ".")
    git("commit", "-m", "v2")
    assert client.post(base + "/jobs").status_code == 201
    assert run_once()
    current = client.get(base).json()
    assert current["snapshot_id"] != old["revision"]
    assert client.get(
        base + "/search/content", params={"q": "python-ast-3"}
    ).json()["results"] == []
    pinned = client.get(
        base + "/search/content", params=old | {"q": "python-ast-3"}
    ).json()
    assert pinned["results"] and pinned["scope"]["historical"]
    assert pinned["results"][0]["path"] == "deep.py"
    # A retired snapshot fails cleanly instead of scanning.
    db.get(Snapshot, old["revision"]).retired_at = utcnow()
    db.commit()
    assert (
        client.get(base + "/search/content", params=old | {"q": "x"}).status_code
        == 410
    )
    for name in store.client().list_graphs():
        if name.startswith("gp_" + repo_id.replace("-", "")):
            store.delete_graph(name)


def test_membership_and_list_pagination(client):
    register(client)
    for name in ("alpha-repo.zip", "beta-repo.zip"):
        assert upload_repo(client, dict(FILES), filename=name)
    base_ids = client.get("/api/repositories", params={"limit": 10}).json()
    assert base_ids["returned"] == 2
    register(client, "outsider@example.com")
    repo_id = base_ids["repositories"][0]["id"]
    base = f"/api/repositories/{repo_id}"
    assert (
        client.get(base + "/search/content", params={"q": "padding"}).status_code
        == 404
    )
    # Pagination metadata over the outsider's empty list stays well-formed.
    empty = client.get("/api/repositories", params={"limit": 5}).json()
    assert empty["returned"] == 0 and empty["has_more"] is False
    register(client, "owner2@example.com")
    for name in ("one.zip", "two.zip", "three.zip"):
        upload_repo(client, {"a.py": "x = 1\n"}, filename=name)
    page = client.get("/api/repositories", params={"limit": 2}).json()
    assert page["returned"] == 2 and page["has_more"] and page["next_offset"] == 2
    rest = client.get(
        "/api/repositories", params={"limit": 2, "offset": page["next_offset"]}
    ).json()
    assert rest["returned"] == 1 and not rest["has_more"]
    filtered = client.get("/api/repositories", params={"q": "two"}).json()
    assert filtered["returned"] == 1 and filtered["repositories"][0]["name"] == "two"
    # The legacy unpaginated shape is preserved.
    legacy = client.get("/api/repositories").json()
    assert isinstance(legacy, list) and len(legacy) == 3


def test_mcp_search_content_and_read_source_parity(client, db, monkeypatch):
    monkeypatch.setattr(settings(), "mcp_enabled", True)
    repo_id = indexed(client, FILES)
    repo = db.get(Repository, repo_id)
    graph_name = repo.graph_name
    token, _ = token_for(db, repo.owner_id)
    try:
        client.headers.pop("Origin", None)
        client.cookies.clear()
        tools = rpc(client, token, "tools/list").json()["result"]["tools"]
        names = {t["name"] for t in tools}
        assert {"search_content", "read_source"} <= names
        hit = rpc(
            client,
            token,
            "tools/call",
            {
                "name": "search_content",
                "arguments": {"repository_id": repo_id, "q": "graph_queries"},
            },
        ).json()["result"]["structuredContent"]["results"][0]
        assert hit["line"] == 235
        source = rpc(
            client,
            token,
            "tools/call",
            {
                "name": "read_source",
                "arguments": {
                    "repository_id": repo_id,
                    "node_id": hit["node_id"],
                    "around": hit["line"],
                },
            },
        ).json()["result"]["structuredContent"]
        assert "graph_queries" in source["content"]
        assert source["start_line"] <= hit["line"] <= source["end_line"]
        listing = rpc(
            client,
            token,
            "tools/call",
            {"name": "list_repositories", "arguments": {"limit": 1}},
        ).json()["result"]["structuredContent"]
        assert listing["limit"] == 1 and "has_more" in listing
        # A token without membership is denied on the new tools too.
        client.headers["Origin"] = "http://testserver"
        outsider = register(client, "mcp-outsider@example.com")
        client.cookies.clear()
        client.headers.pop("Origin", None)
        bad, _ = issue_token(db, db.get(User, outsider["id"]), "outsider", 1)
        db.commit()
        denied = rpc(
            client,
            bad,
            "tools/call",
            {
                "name": "search_content",
                "arguments": {"repository_id": repo_id, "q": "padding"},
            },
        ).json()["result"]
        assert denied["isError"]
        # Revoked membership revokes access on the next call.
        db.add(Membership(repository_id=repo_id, user_id=outsider["id"], permission="read"))
        db.commit()
        allowed = rpc(
            client,
            bad,
            "tools/call",
            {
                "name": "search_content",
                "arguments": {"repository_id": repo_id, "q": "padding", "limit": 1},
            },
        ).json()["result"]["structuredContent"]
        assert allowed["results"]
        db.delete(db.get(Membership, (repo_id, outsider["id"])))
        db.commit()
        denied = rpc(client, bad, "tools/call", {
            "name": "search_content",
            "arguments": {"repository_id": repo_id, "q": "padding"},
        }).json()["result"]
        assert denied["isError"]
    finally:
        store.delete_graph(graph_name)


WIDE_LINE = 'banner = "' + "p" * 15000 + "NEEDLE_WIDE" + "q" * 3000 + '"\n'


def test_overlong_line_column_anchor_serves_the_match(client, db):
    repo_id = indexed(client, {"src/wide.py": WIDE_LINE})
    base = f"/api/repositories/{repo_id}"
    hits = client.get(base + "/search/content", params={"q": "NEEDLE_WIDE"}).json()
    hit = hits["results"][0]
    assert hit["line"] == 1 and hit["column"] > 15000
    # Without a column anchor the bounded excerpt is honestly disclosed as
    # truncated and never claims the hit is inside.
    plain = client.get(
        base + f"/evidence/{hit['node_id']}", params={"around": 1}
    ).json()
    assert plain["truncated"] and "NEEDLE_WIDE" not in plain["content"]
    # The match's own columns anchor a bounded character window that contains
    # the hit, disclosed as a partial line.
    anchored = client.get(
        base + f"/evidence/{hit['node_id']}",
        params={
            "around": hit["line"],
            "column": hit["column"],
            "end_column": hit["end_column"],
        },
    ).json()
    assert "NEEDLE_WIDE" in anchored["content"]
    excerpt = anchored["line_excerpt"]
    assert excerpt["partial"] and excerpt["line"] == 1
    assert excerpt["start_column"] <= hit["column"] < excerpt["end_column"]
    assert excerpt["line_length"] > 12000
    store.delete_graph(db.get(Repository, repo_id).graph_name)


def test_modified_retained_source_fails_integrity_check(client):
    repo_id = indexed(client, FILES)
    base = f"/api/repositories/{repo_id}"
    stats = client.get(base).json()["stats"]
    root = settings().data_dir / "snapshots" / repo_id / stats["tree_hash"]
    node = find_file(client, base, "src/deep.py")
    original = (root / "src/deep.py").read_bytes()
    try:
        # Tamper only inside the retained snapshot: the manifest hash must
        # keep the modified bytes from being served under the pinned snapshot.
        (root / "src/deep.py").write_bytes(
            original.replace(b"X-CSRF-Token", b"X-Corrupted-Token")
        )
        result = client.get(
            base + f"/evidence/{node['id']}", params={"around": 232}
        )
        assert result.status_code == 409, result.text
        assert "X-Corrupted-Token" not in result.text
    finally:
        (root / "src/deep.py").write_bytes(original)


def test_symlinked_snapshot_parent_is_rejected(tmp_path, monkeypatch):
    owned = tmp_path / "owned"
    outside = tmp_path / "outside"
    (owned / "snapshots").mkdir(parents=True)
    tree = "a" * 64
    (outside / tree).mkdir(parents=True)
    (outside / tree / "fixture.txt").write_text("controlled outside content")
    (owned / "snapshots" / "repo-x").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(settings(), "data_dir", owned)
    repo = SimpleNamespace(id="repo-x", stats={"tree_hash": tree})
    with pytest.raises((SourceError, OSError)):
        read_snapshot_bytes(snapshot_root(repo), "fixture.txt", 100)


def test_scan_budgets_charge_attempted_bytes_and_deadline(monkeypatch):
    # Case-insensitive Unicode expansion cannot report the same span twice.
    spans = list(source_search._line_matches("ß", "s", False))
    assert len(spans) == len(set(spans)) == 1
    repo = SimpleNamespace(
        graph_name="g",
        stats={"files": 4},
        branch="main",
        snapshot_id="snap",
        commit_sha="c",
        historical=False,
    )
    rows = [
        {"id": str(i), "path": f"{i}.txt", "content_hash": "0" * 64}
        for i in range(4)
    ]
    requested = []

    def oversized(root, path, limit):
        requested.append(limit + 1)
        return b"x" * limit, True

    monkeypatch.setattr(settings(), "max_file_bytes", 100)
    monkeypatch.setattr(source_search, "file_manifest", lambda *a, **k: (rows, 1, False))
    monkeypatch.setattr(source_search, "snapshot_root", lambda repo: Path("/fixture"))
    monkeypatch.setattr(source_search, "read_snapshot_bytes", oversized)
    monkeypatch.setattr(source_search, "BYTE_BUDGET", 150)
    result = source_search.search_source(repo, "absent", now=lambda: 0)
    assert sum(requested) <= 150  # attempted bounds consume the total budget
    assert result["truncated"] and result["scan"]["bytes_scanned"] >= 150

    # The deadline is enforced inside per-line work, not just between files.
    raw = ("not a match\n" * 100).encode()
    node = {
        "id": "one",
        "path": "one.txt",
        "content_hash": hashlib.sha256(raw).hexdigest(),
    }
    repo.stats = {"files": 1}
    state = {"time": 0.0, "lines": 0}

    def slow_no_match(*args):
        state["time"] += 0.1
        state["lines"] += 1
        return iter(())

    monkeypatch.setattr(source_search, "file_manifest", lambda *a, **k: ([node], 1, False))
    monkeypatch.setattr(
        source_search, "read_snapshot_bytes", lambda *a, **k: (raw, False)
    )
    monkeypatch.setattr(source_search, "_line_matches", slow_no_match)
    monkeypatch.setattr(source_search, "BYTE_BUDGET", 20_000_000)
    monkeypatch.setattr(settings(), "max_file_bytes", 10000)
    result = source_search.search_source(repo, "absent", now=lambda: state["time"])
    assert result["truncated"] and result["completion_reason"] == "time_budget"
    assert state["lines"] < 100


def test_standalone_cr_source_abstains_from_semantic_positions():
    result = parse_file("cr.py", "def one():\r    return 1\rdef two():\r    return 2\r")
    assert result["definitions"] == [] and result["calls"] == []
    assert result["errors"] and "newline" in result["errors"][0]["message"].lower()
    # LF and CRLF controls keep full semantics.
    assert parse_file("lf.py", "def one():\n    return 1\n")["definitions"]
    assert parse_file("crlf.py", "def one():\r\n    return 1\r\n")["definitions"]


def test_impact_and_listing_carry_snapshot_scope(client, db):
    repo_id = indexed(client, FILES)
    base = f"/api/repositories/{repo_id}"
    initial = client.get(base).json()
    symbol = client.get(base + "/search", params={"q": "marker_target"}).json()
    node_id = next(n["id"] for n in symbol["results"] if n["name"] == "marker_target")
    impact = client.get(base + f"/impact/{node_id}").json()
    assert impact["scope"]["snapshot_id"] == initial["snapshot_id"]
    assert impact["scope"]["branch"] == initial["branch"]
    # Repository discovery exposes the current immutable handle.
    listed = client.get("/api/repositories", params={"limit": 5}).json()
    row = next(r for r in listed["repositories"] if r["id"] == repo_id)
    assert row["snapshot_id"] == initial["snapshot_id"]
    legacy = next(
        r for r in client.get("/api/repositories").json() if r["id"] == repo_id
    )
    assert legacy["snapshot_id"] == initial["snapshot_id"]
    # MCP parity on the same two surfaces.
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(settings(), "mcp_enabled", True)
    token, _ = token_for(db, db.get(Repository, repo_id).owner_id)
    client.cookies.clear()
    try:
        listing = rpc(
            client,
            token,
            "tools/call",
            {"name": "list_repositories", "arguments": {"limit": 5}},
        ).json()["result"]["structuredContent"]
        row = next(r for r in listing["repositories"] if r["id"] == repo_id)
        assert row["snapshot_id"] == initial["snapshot_id"]
        impact = rpc(
            client,
            token,
            "tools/call",
            {
                "name": "inspect_impact",
                "arguments": {"repository_id": repo_id, "node_id": node_id},
            },
        ).json()["result"]["structuredContent"]
        assert impact["scope"]["snapshot_id"] == initial["snapshot_id"]
    finally:
        monkeypatch.undo()


def test_result_cap_discloses_partial_even_when_scan_finished(client):
    repo_id = indexed(client, {"a.txt": "hit\nhit\nhit\nhit\n", "b.txt": "none\n"})
    base = f"/api/repositories/{repo_id}"
    body = client.get(
        base + "/search/content", params={"q": "hit", "limit": 2}
    ).json()
    # The whole manifest was scanned but the response was cut by `limit` —
    # the partial answer must not look complete.
    assert body["scan_complete"] is True
    assert body["truncated"] is True and body["has_more"] is True
    assert body["completion_reason"] == "result_limit"
    assert body["total"] == 4  # exact: the scan provably finished
    assert body["returned"] == 2


def test_multiline_literal_and_shared_filter_validation(client, db):
    repo_id = indexed(client, FILES)
    base = f"/api/repositories/{repo_id}"
    # Multi-line literals are rejected explicitly, never a silent empty scan.
    for q in ("one\ntwo", "carriage\rreturn"):
        assert (
            client.get(base + "/search/content", params={"q": q}).status_code == 422
        )
    # The same unsafe filters fail on MCP, sharing the HTTP schema.
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(settings(), "mcp_enabled", True)
    token, _ = token_for(db, db.get(Repository, repo_id).owner_id)
    client.cookies.clear()
    try:
        for args in (
            {"q": "x", "path": "../escape"},
            {"q": "x", "suffix": "a/b"},
            {"q": "line1\nline2"},
        ):
            result = rpc(
                client,
                token,
                "tools/call",
                {
                    "name": "search_content",
                    "arguments": {"repository_id": repo_id} | args,
                },
            ).json()["result"]
            assert result["isError"], args
    finally:
        monkeypatch.undo()


def test_snapshots_base_symlink_is_rejected(tmp_path, monkeypatch):
    # The owned `snapshots` component itself being a link must not be followed
    # — even when it points inside the owned root.
    owned = tmp_path / "owned"
    shadow = owned / "shadow"
    tree = "a" * 64
    repo_id = "00000000-0000-0000-0000-000000000123"
    (shadow / repo_id / tree).mkdir(parents=True)
    (shadow / repo_id / tree / "fixture.txt").write_text("controlled alternate")
    (owned / "snapshots").symlink_to(shadow, target_is_directory=True)
    monkeypatch.setattr(settings(), "data_dir", owned)
    repo = SimpleNamespace(id=repo_id, stats={"tree_hash": tree})
    with pytest.raises((SourceError, OSError)):
        read_snapshot_bytes(snapshot_root(repo), "fixture.txt", 100)


def test_context_budget_contains_late_long_line_match(client):
    # A 20KB prefix + suffix pushes the match beyond any flat excerpt cut:
    # the per-citation budget must recenter the column-anchored window, not
    # silently drop the hit while claiming line_excerpt coverage.
    long_line = "q" * 20000 + "PARENT_LATE_MATCH" + "z" * 4000 + "\n"
    repo_id = indexed(client, {"long.txt": long_line})
    base = f"/api/repositories/{repo_id}"
    hit = client.get(
        base + "/search/content", params={"q": "PARENT_LATE_MATCH"}
    ).json()["results"][0]
    assert hit["column"] == 20001
    answer = client.post(
        base + "/context",
        json={
            "question": "Explain selected source",
            "source": {
                "node_id": hit["node_id"],
                "around": hit["line"],
                "column": hit["column"],
                "end_column": hit["end_column"],
            },
        },
    ).json()
    pinned = next(c for c in answer["evidence"] if c.get("pinned"))
    assert "PARENT_LATE_MATCH" in pinned["content"]
    assert len(pinned["content"]) <= 3000
    excerpt = pinned["line_excerpt"]
    assert excerpt and excerpt["partial"] and excerpt["line"] == 1
    assert excerpt["start_column"] <= hit["column"]
    assert excerpt["end_column"] >= hit["end_column"] - 1
    # The served window omitted the suffix: the final line is honestly partial.
    assert pinned["end_line_partial"] is True
    assert pinned["truncated"] is True
    assert pinned["content_hash"]
    assert len(answer["evidence"]) <= 8
    assert sum(len(c["content"]) for c in answer["evidence"]) <= 24000


def test_pinned_and_retrieved_identical_column_windows_dedupe(client):
    repo_id = indexed(client, FILES)
    base = f"/api/repositories/{repo_id}"
    hit = next(
        h
        for h in client.get(
            base + "/search/content", params={"q": "X-CSRF-Token"}
        ).json()["results"]
        if h["path"] == "src/deep.py"
    )
    answer = client.post(
        base + "/context",
        json={
            "question": 'Where is "X-CSRF-Token" set?',
            "source": {
                "node_id": hit["node_id"],
                "around": hit["line"],
                "column": hit["column"],
                "end_column": hit["end_column"],
            },
        },
    ).json()
    spans = [c for c in answer["evidence"] if c["entity_id"] == hit["node_id"]]
    # The pinned selection and the retrieved literal hit resolve to the same
    # bounded span — served once.
    assert len(spans) == 1 and spans[0]["pinned"]
    assert spans[0]["content_hash"]


def test_graph_query_accounting_counts_failed_scan_and_impact_lookup(
    client, monkeypatch
):
    repo_id = indexed(client, FILES)
    base = f"/api/repositories/{repo_id}"
    calls = []
    real_query = store.query

    def counted(graph, statement, params=None, **kwargs):
        calls.append(statement)
        return real_query(graph, statement, params, **kwargs)

    # A literal scan that fails after its manifest query must still be counted.
    def unavailable(repo):
        raise SourceError("Controlled unavailable artifact")

    monkeypatch.setattr(store, "query", counted)
    monkeypatch.setattr(source_search, "snapshot_root", unavailable)
    answer = client.post(
        base + "/context", json={"question": 'Find "never-present-literal"'}
    ).json()
    monkeypatch.undo()
    assert answer["diagnostics"]["literal_scan_failed"] is True
    assert answer["diagnostics"]["graph_queries"] == len(calls)

    # The HTTP impact wrapper's own existence lookup is counted too.
    symbol = client.get(base + "/search", params={"q": "marker_target"}).json()
    node_id = next(n["id"] for n in symbol["results"] if n["name"] == "marker_target")
    calls.clear()
    monkeypatch.setattr(store, "query", counted)
    result = client.get(base + f"/impact/{node_id}").json()
    monkeypatch.undo()
    assert result["graph_queries"] == len(calls)
