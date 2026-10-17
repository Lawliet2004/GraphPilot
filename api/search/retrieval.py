"""Deterministic evidence retrieval with explicit limits and diagnostics."""

import re
import time

from api.graph import store

STOPWORDS = {
    "the",
    "and",
    "for",
    "what",
    "does",
    "this",
    "that",
    "which",
    "with",
    "from",
    "call",
    "calls",
    "callers",
    "find",
    "show",
    "explain",
    "function",
    "functions",
    "file",
    "files",
    "how",
    "are",
    "why",
    "when",
    "where",
    "was",
    "were",
    "into",
    "have",
    "has",
    "who",
    "dependencies",
    "dependency",
    "impact",
    "issue",
    "commit",
    "failing",
    "failure",
    "test",
    "tests",
    "of",
    "to",
    "a",
    "an",
    "is",
    "in",
    "by",
    "it",
    "its",
    "me",
    "can",
    "you",
    "investigate",
    "identify",
    "related",
    "modified",
    "changed",
    "pull",
    "request",
    "pr",
    "ci",
    "failed",
    "chain",
    "between",
    "downstream",
    "upstream",
    "please",
}


def interpret(question):
    lower = question.lower()
    issue = re.search(r"\bissue\s*#?\s*(\d+)\b", lower)
    pull = re.search(r"\b(?:pr|pull request)\s*#?\s*(\d+)\b", lower)
    intent = (
        "issue"
        if issue
        else "pull_request"
        if pull
        else "ci_failure"
        if re.search(r"\b(?:ci|workflow|failed|failing|failure)\b", lower)
        else "impact"
        if re.search(r"\b(?:impact|downstream)\b", lower)
        else "dependency"
        if re.search(r"\b(?:callers?|calls|dependencies|dependency|chain)\b", lower)
        else "lookup"
    )
    if issue or pull:
        return intent, [("#" + (issue or pull)[1], "Issue" if issue else "PullRequest", "")]
    shas = re.findall(r"\b[0-9a-fA-F]{7,40}\b", question)
    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_./-]*|#[0-9]+", question)
    candidates = sorted(
        set(shas) | {t.rstrip(".") for t in tokens if t.lower() not in STOPWORDS and len(t) > 1},
        key=lambda t: (t not in shas, "_" not in t and "." not in t, -len(t), t),
    )[:5]
    lookups = [
        (t, "Commit" if t in shas else "File" if t.endswith(".py") else "", "") for t in candidates
    ]
    if intent == "ci_failure":
        lookups = [("", "WorkflowRun", "failure")] + lookups[:4]
    return intent, lookups


def retrieve(repo, question):
    started = time.perf_counter()
    intent, lookups = interpret(question)
    results, edges, graph_queries = {}, {}, 0
    # One bounded lookup per distinct useful identifier. Never retry the same term.
    for term, kind, status in lookups:
        graph_queries += 1
        for result in store.search(repo.graph_name, term, limit=10, kind=kind, status=status):
            if result["id"] not in results or results[result["id"]]["score"] < result["score"]:
                results[result["id"]] = result
    ranked = sorted(results.values(), key=lambda r: (-r["score"], r["id"]))[:12]
    queue, visited = list(ranked[:2]), set()
    relation = "CALLS" if intent in {"dependency", "impact"} else None
    for _ in range(2):
        if not queue:
            break
        seed = queue.pop(0)
        if seed["id"] in visited:
            continue
        visited.add(seed["id"])
        neighborhood = store.neighbors(repo.graph_name, seed["id"], limit=30, relation=relation)
        graph_queries += 1
        for edge in neighborhood["edges"]:
            edges[edge["id"]] = edge
        for node in neighborhood["nodes"]:
            if node["id"] not in results:
                results[node["id"]] = {
                    **node,
                    "score": 0.35 if seed.get("distance", 0) == 0 else 0.25,
                    "distance": seed.get("distance", 0) + 1,
                    "score_meaning": f"{seed.get('distance', 0) + 1} recorded graph relationships from a search match",
                    "uncertainty": "Static relationship; runtime behavior is unverified.",
                }
        if not queue:
            priority = [
                "PullRequest",
                "Commit",
                "WorkflowRun",
                "LogArtifact",
                "TestCase",
                "Function",
                "File",
            ]
            if intent == "ci_failure":
                priority = ["LogArtifact", "TestCase", "Commit", "PullRequest", "Function", "File"]
            queue = sorted(
                [
                    results[n["id"]]
                    for n in neighborhood["nodes"]
                    if n["id"] not in visited and n["type"] in priority
                ],
                key=lambda n: (priority.index(n["type"]), n["id"]),
            )[:1]
    results = sorted(results.values(), key=lambda r: (-r["score"], r["id"]))[:20]
    ids = {n["id"] for n in results}
    edges = [e for e in edges.values() if e["source"] in ids and e["target"] in ids]
    return {
        "results": results,
        "relationships": edges,
        "branch": repo.branch,
        "commit": repo.commit_sha,
        "warnings": ["Dynamic dispatch and external packages are not resolved."]
        + (
            []
            if results
            else [
                "No matching evidence was found. Try an exact symbol, filename, issue number or commit SHA."
            ]
        ),
        "diagnostics": {
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "graph_queries": graph_queries,
            "max_tool_calls": 7,
            "max_depth": 2,
            "intent": intent,
            "returned_nodes": len(results),
            "context_bytes": len(str(results).encode()),
            "ranking": "1.0 exact identifier/path; 0.95 SHA prefix; 0.8 name prefix; 0.55 name/path/status; 0.4 metadata text; 0.35 direct or 0.25 second-hop neighbor. Scores measure relevance, not certainty.",
        },
    }
