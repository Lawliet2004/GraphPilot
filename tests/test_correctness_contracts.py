"""Regression contracts for defects reproduced by the competitive research.

Parser fixtures come from adversarial-probes.json; the impact fixtures come
from correctness-probes.json (a direct caller must not be mislabeled at
distance 2, and a capped result must disclose incompleteness); the citation
fixture reproduces the context route's stale range metadata. Controls pin the
behavior that was already correct.
"""

import hashlib
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import api.routes.context as context_route
from api.graph import store
from api.ingestion.python import build_graph, parse_file
from api.ingestion.sources import SourceError
from api.search.retrieval import interpret
from api.services.source_ranges import bounded_slice, read_source_range


def graph_for(sources):
    files = {
        path: {
            "hash": hashlib.sha256(source.encode()).hexdigest(),
            "lines": len(source.splitlines()),
            "parsed": parse_file(path, source),
        }
        for path, source in sources.items()
    }
    nodes, edges, stats = build_graph("contract", "main", "commit", "probe", files)
    names = {n["id"]: n["original_id"] for n in nodes}
    calls = {
        (names[e["source"]], names[e["target"]]) for e in edges if e["type"] == "CALLS"
    }
    return calls, stats


def test_rebound_self_abstains_but_constructor_still_resolves():
    calls, stats = graph_for(
        {
            "m.py": "class Other:\n"
            "    def target(self):\n"
            "        return 'other'\n"
            "class Caller:\n"
            "    def target(self):\n"
            "        return 'caller'\n"
            "    def run(self):\n"
            "        self = Other()\n"
            "        return self.target()\n"
        }
    )
    # self.target() must not land on Caller.target after self is rebound.
    assert ("m.py:Caller.run", "m.py:Caller.target") not in calls
    assert ("m.py:Caller.run", "m.py:Other") in calls  # Other() is still direct
    assert stats["resolved_calls"] == 1 and stats["unresolved_calls"] == 1


def test_self_call_control_still_resolves():
    calls, stats = graph_for(
        {
            "m.py": "class C:\n"
            "    def helper(self):\n"
            "        return 1\n"
            "    def run(self):\n"
            "        return self.helper()\n"
        }
    )
    assert ("m.py:C.run", "m.py:C.helper") in calls
    assert stats["unresolved_calls"] == 0


def test_module_function_replaced_by_lambda_abstains():
    calls, stats = graph_for(
        {
            "m.py": "def target():\n"
            "    return 'old'\n"
            "target = lambda: 'replacement'\n"
            "target()\n"
        }
    )
    # The declaration is stale by the call site; keeping the edge would lie.
    assert not calls
    assert stats["resolved_calls"] == 0 and stats["unresolved_calls"] == 1


def test_module_call_before_rebinding_still_resolves():
    calls, stats = graph_for(
        {
            "m.py": "def target():\n"
            "    return 'old'\n"
            "target()\n"
            "target = lambda: 'replacement'\n"
        }
    )
    # At line 3 the def is still the module binding.
    assert ("m.py", "m.py:target") in calls


def test_function_local_rebound_control_stays_unresolved():
    calls, stats = graph_for(
        {
            "m.py": "def target():\n"
            "    return 'old'\n"
            "def run():\n"
            "    target = lambda: 'replacement'\n"
            "    return target()\n"
        }
    )
    assert not calls and stats["unresolved_calls"] == 1


def test_missing_import_control_keeps_same_named_definition_unlinked():
    calls, stats = graph_for(
        {
            "unrelated.py": "def target():\n    return 'unrelated'\n",
            "caller.py": "from missing_package import target\n"
            "def run():\n"
            "    return target()\n",
        }
    )
    assert not calls and stats["unresolved_calls"] == 1


def test_import_rebinding_supersedes_earlier_local_def():
    # Held-out review fixture: the import is the live binding, so the obsolete
    # local def must not receive the call edge even though it shares the name.
    calls, stats = graph_for(
        {
            "caller.py": "def target():\n    pass\n"
            "from nonexistent import target\n"
            "def run():\n"
            "    return target()\n",
        }
    )
    assert not calls and stats["unresolved_calls"] == 1


def test_import_rebinding_resolves_through_import_map():
    calls, _ = graph_for(
        {
            "pkg/__init__.py": "",
            "pkg/impl.py": "def target():\n    return 'real'\n",
            "caller.py": "def target():\n    pass\n"
            "from pkg.impl import target\n"
            "def run():\n"
            "    return target()\n",
        }
    )
    assert ("caller.py:run", "pkg/impl.py:target") in calls
    assert ("caller.py:run", "caller.py:target") not in calls


def test_invalid_relative_import_does_not_fall_back_to_stale_def():
    calls, stats = graph_for(
        {
            "caller.py": "def target():\n    pass\n"
            "from ..sib import target\n"
            "def run():\n"
            "    return target()\n",
            "sib.py": "def target():\n    return 'sibling'\n",
        }
    )
    assert not calls and stats["unresolved_calls"] == 1
    assert any("escapes the top-level package" in e["message"] for e in stats["parse_errors"])


def test_relative_import_beyond_top_level_abstains_and_discloses():
    calls, stats = graph_for(
        {
            "target.py": "def target():\n    return 'top-level'\n",
            "caller.py": "from ...target import target\n"
            "def run():\n"
            "    return target()\n",
        }
    )
    # importlib.resolve_name raises ImportError here; the top-level module must
    # not be picked up as a lookalike target.
    assert ("caller.py:run", "target.py:target") not in calls
    assert stats["unresolved_calls"] == 1
    assert any("escapes the top-level package" in e["message"] for e in stats["parse_errors"])


def test_relative_import_boundary_matches_importlib():
    # . and .. resolve inside the package; one more dot escapes it.
    calls, _ = graph_for(
        {
            "pkg/__init__.py": "",
            "pkg/target.py": "def target():\n    return 1\n",
            "pkg/sub/mod.py": "from ..target import target\n"
            "def run():\n"
            "    return target()\n",
        }
    )
    assert ("pkg/sub/mod.py:run", "pkg/target.py:target") in calls
    _, stats = graph_for(
        {
            "pkg/__init__.py": "",
            "pkg/target.py": "def target():\n    return 1\n",
            "pkg/sub/__init__.py": "from ...target import target\n",
        }
    )
    assert any("escapes the top-level package" in e["message"] for e in stats["parse_errors"])
    _, stats = graph_for(
        {
            "pkg/__init__.py": "from ..sib import x\n",
            "sib.py": "x = 1\n",
        }
    )
    # from .. import inside a package __init__ escapes, matching resolve_name.
    assert any("escapes the top-level package" in e["message"] for e in stats["parse_errors"])


def test_init_relative_import_resolves():
    calls, stats = graph_for(
        {
            "pkg/__init__.py": "from .target import target\ndef run():\n    return target()\n",
            "pkg/target.py": "def target():\n    return 1\n",
        }
    )
    assert ("pkg/__init__.py:run", "pkg/target.py:target") in calls


def impact_graph(nodes, edges):
    name = "test_impact_" + uuid.uuid4().hex[:12]
    store.create_graph(name, nodes, edges)
    return name


def entity(node_id):
    return {
        "id": node_id,
        "type": "Function",
        "name": node_id,
        "original_id": node_id,
        "provenance": "static",
    }


def edge(source, target, line=0):
    return {"source": source, "target": target, "type": "CALLS", "line": line}


def test_direct_caller_is_not_mislabeled_by_indirect_paths():
    # correctness-probes fixture: caller has a direct edge plus many two-hop
    # paths through relays; both insertion orders must report distance 1.
    for mode in ("direct_first", "direct_last"):
        nodes = [entity("target"), entity("caller")]
        nodes += [entity(f"relay{i}") for i in range(110)]
        edges = []
        if mode == "direct_first":
            edges.append(edge("caller", "target"))
        edges += [edge("caller", f"relay{i}") for i in range(110)]
        edges += [edge(f"relay{i}", "target") for i in range(110)]
        if mode == "direct_last":
            edges.append(edge("caller", "target"))
        name = impact_graph(nodes, edges)
        try:
            result = store.impact(name, "target", 2)
        finally:
            store.delete_graph(name)
        caller = next(r for r in result["results"] if r["node"]["id"] == "caller")
        assert caller["distance"] == 1, mode
        assert caller["classification"] == "verified static direct dependency"
        assert [n["id"] for n in caller["path"]] == ["caller", "target"]
        assert len(caller["relationships"]) == 1


def test_capped_result_discloses_incomplete_metadata():
    nodes = [entity("target")] + [entity(f"caller{i}") for i in range(105)]
    edges = [edge(f"caller{i}", "target") for i in range(105)]
    name = impact_graph(nodes, edges)
    try:
        result = store.impact(name, "target", 1)
    finally:
        store.delete_graph(name)
    # All 105 callers were found; only 100 are returned, and that is disclosed.
    assert result["returned"] == 100 and len(result["results"]) == 100
    assert result["total"] == 105  # traversal completed: exact within-depth count
    assert result["has_more"] and result["truncated"]
    assert result["traversal_complete"] is True
    assert result["completion_reason"] == "result_limit"
    assert all(r["distance"] == 1 for r in result["results"])


def test_interrupted_layer_stops_before_deeper_distances(monkeypatch):
    monkeypatch.setattr(store, "IMPACT_LAYER_EDGE_LIMIT", 5)
    nodes = [entity("target")] + [entity(f"caller{i}") for i in range(20)]
    edges = [edge(f"caller{i}", "target") for i in range(20)]
    edges += [edge("deeper", c) for c in [f"caller{i}" for i in range(20)]]
    nodes.append(entity("deeper"))
    name = impact_graph(nodes, edges)
    try:
        result = store.impact(name, "target", 2)
    finally:
        store.delete_graph(name)
    assert result["truncated"] and result["completion_reason"] == "edge_limit"
    assert result["traversal_complete"] is False
    assert result["total"] is None  # exact counts only when traversal completed
    assert all(r["distance"] == 1 for r in result["results"])
    assert result["returned"] == len(result["results"]) <= 5


def test_cycles_and_duplicate_edges_stay_bounded():
    nodes = [entity(n) for n in ("target", "a", "b")]
    edges = [
        edge("b", "target"),
        edge("a", "b"),
        edge("b", "a"),  # cycle a <-> b
        edge("target", "a"),  # the target itself calls a: not a caller result
        edge("a", "target"),  # duplicate second direct edge at another line
        edge("a", "target", line=9),
    ]
    name = impact_graph(nodes, edges)
    try:
        result = store.impact(name, "target", 3)
    finally:
        store.delete_graph(name)
    by_id = {r["node"]["id"]: r for r in result["results"]}
    assert by_id["b"]["distance"] == 1
    assert by_id["a"]["distance"] == 1  # direct edge wins over a->b->target
    assert "target" not in by_id
    assert result["completion_reason"] == "exhausted"
    assert result["total"] == 2 and not result["truncated"]
    # Every returned witness path ends at the target and respects direction.
    for row in result["results"]:
        assert row["path"][0]["id"] == row["node"]["id"]
        assert row["path"][-1]["id"] == "target"
        assert len(row["relationships"]) == row["distance"]


def test_failed_frontier_query_still_counts_and_discloses(monkeypatch):
    nodes = [entity("target"), entity("caller")]
    edges = [edge("caller", "target")]
    name = impact_graph(nodes, edges)
    real_query = store.query

    def flaky(graph, cypher, params=None, readonly=True):
        if "caller" in cypher:
            raise TimeoutError("frontier query timed out")
        return real_query(graph, cypher, params=params, readonly=readonly)

    monkeypatch.setattr(store, "query", flaky)
    try:
        result = store.impact(name, "target", 2)
    finally:
        store.delete_graph(name)
    # Two store.query attempts happened: the node lookup and the failed
    # frontier query. Both are counted, and the failure is disclosed.
    assert result["graph_queries"] == 2
    assert result["completion_reason"] == "time_budget"
    assert result["truncated"] and result["traversal_complete"] is False
    assert result["total"] is None and result["results"] == []


def test_depth_limit_is_a_declared_scope_not_truncation():
    nodes = [entity(n) for n in ("target", "a", "b", "c")]
    edges = [edge("a", "target"), edge("b", "a"), edge("c", "b")]
    name = impact_graph(nodes, edges)
    try:
        result = store.impact(name, "target", 1)
    finally:
        store.delete_graph(name)
    assert [r["node"]["id"] for r in result["results"]] == ["a"]
    assert result["completion_reason"] == "depth_limit"
    assert result["traversal_complete"] is True
    assert not result["truncated"] and result["total"] == 1
    assert result["max_depth"] == 1


def citation_fixture(content, start_line=1, end_line=200, truncated=False):
    evidence = {
        "content": content,
        "start_line": start_line,
        "end_line": end_line,
        "truncated": truncated,
        "commit": "synthetic-commit",
        "url": "https://example.invalid/source",
    }
    retrieved = {
        "results": [
            {"id": "fixture", "name": "fixture", "type": "Function", "path": "fixture.py"}
        ],
        "relationships": [],
        "warnings": [],
        "diagnostics": {"graph_queries": 0},
    }

    class FakeDB:
        def scalars(self, *args):
            return []

        def add(self, row):
            self.row = row

        def commit(self):
            pass

    repo = SimpleNamespace(
        id="research", branch="main", snapshot_id="synthetic", historical=False
    )
    with (
        patch.object(context_route, "indexed"),
        patch.object(context_route, "retrieve", return_value=retrieved),
        patch.object(context_route, "read_evidence", return_value=evidence),
        patch.object(context_route, "for_synthesis", return_value=None),
        patch.object(
            context_route,
            "synthesize",
            return_value={"mode": "graph", "answer": None},
        ),
    ):
        response = context_route.context(
            "research",
            context_route.Question(question="fixture"),
            user=SimpleNamespace(id="fake"),
            db=FakeDB(),
            repo=repo,
        )
    return response["evidence"][0]


def test_served_citation_range_matches_actual_excerpt():
    # correctness-probes fixture: 8000 characters over 200 lines, capped at
    # 3000 -> exactly 75 complete 40-character lines are served.
    source = "".join(f"line {i:03d} " + "x" * 30 + "\n" for i in range(1, 201))
    citation = citation_fixture(source, 1, 200)
    assert len(citation["content"]) == 3000
    assert citation["start_line"] == 1
    assert citation["end_line"] == 75
    assert citation["truncated"] is True
    assert citation["end_line_partial"] is False


def test_citation_partial_final_line_is_disclosed():
    # A U+2028 inside the last served line must not inflate the line count:
    # LF-only accounting reports line 31 where splitlines() would report 32.
    source = ("x" * 99 + "\n") * 29  # 2900 chars, 29 lines
    source += "y" * 90 + "\u2028zz\n"  # line 30: 95 chars -> 2995
    source += "tail" * 30  # line 31: 120 chars, no trailing newline
    excerpt = bounded_slice(source, 1, 31, 3000)
    assert excerpt["end_line"] == 31
    assert excerpt["end_line_partial"] is True
    assert excerpt["truncated"] is True


def test_trailing_delimiter_belongs_to_its_line():
    excerpt = bounded_slice("line1\nline2\n", 1, 3, 100)
    assert excerpt["end_line"] == 2 and not excerpt["end_line_partial"]
    assert excerpt["truncated"] is False


def test_empty_excerpt_can_still_be_truncated():
    excerpt = bounded_slice("content exists upstream", 4, 9, 0, upstream_truncated=True)
    assert excerpt["content"] == ""
    assert excerpt["truncated"] is True
    assert excerpt["start_line"] == 4 and excerpt["end_line"] == 3


def test_non_source_evidence_keeps_null_range():
    excerpt = bounded_slice("body text", None, None, 5)
    assert excerpt["start_line"] is None and excerpt["end_line"] is None
    assert excerpt["truncated"] is True and excerpt["end_line_partial"] is None


def test_unicode_and_crlf_line_semantics_are_explicit():
    # Source lines are LF-delimited only, matching AST line numbers: U+2028
    # and CR stay inside a line rather than inventing a line the parser never
    # saw.
    excerpt = bounded_slice("a\u2028b\nc\r\nd", 1, 4, 100)
    assert excerpt["end_line"] == 3  # 'a\u2028b', 'c\r', 'd'
    assert bounded_slice("x\r\ny\n", 1, 2, 100)["end_line"] == 2
    # A cut before U+2028 lands mid-source-line; a cut before LF does not.
    assert bounded_slice("ab\u2028cd", 1, 2, 2)["end_line_partial"] is True
    assert bounded_slice("ab\ncd", 1, 2, 4)["end_line_partial"] is True
    assert bounded_slice("ab\ncd", 1, 2, 3)["end_line_partial"] is False


def test_absent_upstream_truncation_stays_unknown():
    excerpt = bounded_slice("complete body", 1, 1, 5000, upstream_truncated=None)
    assert excerpt["truncated"] is None
    assert excerpt["end_line_partial"] is False
    cut = bounded_slice("partial body", 1, 1, 4, upstream_truncated=None)
    assert cut["truncated"] is True


def test_exact_log_boundary_is_not_truncated():
    content = "x" * 12000
    excerpt = bounded_slice(content, 1, None, 12000)
    assert excerpt["truncated"] is False
    excerpt = bounded_slice("x" * 12001, 1, None, 12000)
    assert excerpt["truncated"] is True and excerpt["end_line_partial"] is True


def test_read_source_range_window_and_explicit_range(tmp_path):
    source = "".join(f"line {i:03d}\n" for i in range(1, 301))
    (tmp_path / "big.py").write_text(source)
    served = read_source_range(tmp_path, "big.py", 100, 105, context=3)
    assert (served["start_line"], served["end_line"]) == (97, 108)
    assert "line 100" in served["content"] and not served["truncated"]
    # An explicit range read reaches text beyond the 200-line entity window.
    served = read_source_range(tmp_path, "big.py", 250, 260)
    assert (served["start_line"], served["end_line"]) == (250, 260)
    assert "line 255" in served["content"]
    # The file continues beyond a range that hit the line cap: disclosed.
    served = read_source_range(tmp_path, "big.py", 1, 300)
    assert served["truncated"] and served["end_line"] == 200


def test_read_source_range_rejects_unsafe_and_empty(tmp_path):
    (tmp_path / "real.py").write_text("ok\n")
    (tmp_path / "linked.py").write_text("nope\n")
    (tmp_path / "real.py").unlink(missing_ok=True)
    (tmp_path / "link.py").symlink_to(tmp_path / "linked.py")
    with pytest.raises(SourceError):
        read_source_range(tmp_path, "link.py", 1, 1)
    with pytest.raises(SourceError):
        read_source_range(tmp_path, "../outside.py", 1, 1)
    with pytest.raises(SourceError):
        read_source_range(tmp_path, "missing.py", 1, 1)
    (tmp_path / "empty.py").write_text("")
    served = read_source_range(tmp_path, "empty.py", 1, 5)
    assert served["content"] == "" and served["end_line"] == 0


def test_payment_failure_is_not_ci_intent():
    intent, _ = interpret("How is payment failure handled?")
    assert intent != "ci_failure"
    intent, _ = interpret("Handle the error message returned by checkout")
    assert intent != "ci_failure"


def test_existing_ci_intents_still_route():
    for question in (
        "Investigate failing CI",
        "Why is the workflow failing?",
        "the deploy failed again",
        "which tests failed in the pipeline",
    ):
        assert interpret(question)[0] == "ci_failure", question
        intent, lookups = interpret(question)
        assert ("", "WorkflowRun", "failure") in lookups


def test_quoted_literals_and_paths_become_lookup_terms():
    _, lookups = interpret('Where is "X-CSRF-Token" set?')
    assert ("X-CSRF-Token", "", "") in lookups
    _, lookups = interpret("Find `Request origin is not allowed` in the code")
    assert ("Request origin is not allowed", "", "") in lookups
    _, lookups = interpret("what does api/routes/context.py do")
    assert ("api/routes/context.py", "File", "") in lookups
    _, lookups = interpret("Find normalize")
    assert ("normalize", "", "") in lookups
