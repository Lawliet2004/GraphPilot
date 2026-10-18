"""Deterministic evidence retrieval with explicit limits and diagnostics."""

import re
import time

from api.graph import store
from api.ingestion.sources import SourceError
from api.services import source_search

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
    "any",
    "new",
    "could",
    "would",
    "should",
    "some",
    "about",
    "better",
    "make",
    "add",
    "want",
    "need",
    "help",
    "using",
    "used",
    "we",
    "our",
    "my",
    "your",
}


# A file-path-looking term narrows the lookup to File nodes. Other source and
# text extensions get the same treatment as Python files.
SOURCE_PATH = re.compile(
    r"(?:^|[/\\])[^\s/\\]+\.(?:py|pyi|js|jsx|ts|tsx|mjs|cjs|go|rs|java|rb|php|"
    r"c|cc|cpp|h|hpp|cs|md|markdown|txt|json|toml|yaml|yml|sql|css|scss|html|"
    r"xml|sh|bash|cfg|ini|env|lock)$|\.(?:py|pyi|js|jsx|ts|tsx|mjs|cjs|go|rs|java|"
    r"rb|php|c|cc|cpp|h|hpp|cs|md|markdown|txt|json|toml|yaml|yml|sql|css|scss|"
    r"html|xml|sh|bash|cfg|ini|env|lock)$",
    re.IGNORECASE,
)

# Quoted literals keep their punctuation and spacing as exact lookup phrases.
QUOTED_LITERAL = re.compile(r'"([^"\n]{1,300})"|\'([^\'\n]{1,300})\'|`([^`\n]{1,300})`')

# CI failure intent requires both a failure signal and workflow context, so
# "payment failure" does not route to CI.
FAILURE_WORD = re.compile(r"\b(?:fail(?:s|ed|ing|ures?)?|errors?|broken|crash(?:es|ed|ing)?)\b")
CI_CONTEXT = re.compile(
    r"\b(?:ci|workflows?|pipelines?|builds?|jobs?|actions?|deploy(?:ed|ing|ments?|s)?|"
    r"releases?|checks?|suites?|tests?|gitlab|circleci|jenkins|travis|appveyor)\b"
)
TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_./-]*")


def _intent_text(lower):
    """Question text for intent matching with lookup data removed.

    Quoted literals and explicit file locations are search terms, not
    workflow context: 'Find "job failure" in messages.txt' is a content
    lookup, not a CI question.
    """
    masked = QUOTED_LITERAL.sub(" ", lower)
    return TOKEN.sub(
        lambda m: " "
        if "/" in m[0] or "\\" in m[0] or SOURCE_PATH.search(m[0])
        else m[0],
        masked,
    )


def interpret(question):
    lower = question.lower()
    intent_text = _intent_text(lower)
    issue = re.search(r"\bissue\s*#?\s*(\d+)\b", lower)
    pull = re.search(r"\b(?:pr|pull request)\s*#?\s*(\d+)\b", lower)
    intent = (
        "issue"
        if issue
        else "pull_request"
        if pull
        else "ci_failure"
        if FAILURE_WORD.search(intent_text) and CI_CONTEXT.search(intent_text)
        else "impact"
        if re.search(r"\b(?:impact|downstream)\b", lower)
        else "dependency"
        if re.search(r"\b(?:callers?|calls|dependencies|dependency|chain)\b", lower)
        else "overview"
        if re.search(
            r"\b(?:overview|summari[sz]e|architecture|features?|improv\w*|user experience|"
            r"understand|what (?:is|does) (?:this|the) (?:app|project|repo\w*))\b",
            lower,
        )
        else "lookup"
    )
    if issue or pull:
        return intent, [("#" + (issue or pull)[1], "Issue" if issue else "PullRequest", "")]
    literals = [
        group.strip()
        for match in QUOTED_LITERAL.findall(question)
        for group in match
        if group and group.strip()
    ]
    shas = re.findall(r"\b[0-9a-fA-F]{7,40}\b", question)
    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_./-]*|#[0-9]+", question)
    candidates = sorted(
        set(shas) | {t.rstrip(".") for t in tokens if t.lower() not in STOPWORDS and len(t) > 1},
        key=lambda t: (t not in shas, "_" not in t and "." not in t, -len(t), t),
    )
    lookups = [(literal, "", "") for literal in literals[:2]]
    lookups += [
        (
            t,
            "Commit"
            if t in shas
            else "File"
            if "/" in t or "\\" in t or SOURCE_PATH.search(t)
            else "",
            "",
        )
        for t in candidates[: 5 - len(lookups)]
    ]
    if intent == "ci_failure":
        lookups = [("", "WorkflowRun", "failure")] + lookups[:4]
    return intent, lookups


def retrieve(repo, question, previous_question=None):
    started = time.perf_counter()
    intent, lookups = interpret(question)
    follow_up = (
        bool(previous_question)
        and len(question.split()) <= 12
        and bool(
            re.search(r"\b(?:it|that|those|these|more|instead|also|suggestion)\b", question.lower())
        )
    )
    if follow_up:
        previous_intent, previous_lookups = interpret(previous_question)
        if intent == "lookup":
            intent = previous_intent
        lookups = list(dict.fromkeys(previous_lookups + lookups))[:5]
    results, edges, graph_queries = {}, {}, 0
    # One bounded lookup per distinct useful identifier. Never retry the same term.
    for term, kind, status in lookups:
        graph_queries += 1
        for result in store.search(
            repo.graph_name, term, limit=10, kind=kind, status=status, include_docs=True
        ):
            if result["id"] not in results or results[result["id"]]["score"] < result["score"]:
                results[result["id"]] = result
    # Quoted literals also run through the snapshot content scanner so a phrase
    # inside a file body surfaces its File node with the exact match position.
    # The literal text is used verbatim — never stripped or regex-interpreted.
    literals = [
        group
        for match in QUOTED_LITERAL.findall(question)
        for group in match
        if group and len(group) <= source_search.QUERY_MAX
    ][:2]
    literal_scan_failed = False
    for literal in literals:
        try:
            found = source_search.search_source(repo, literal, case_sensitive=False, limit=10)
        except SourceError as exc:
            # A failed scan may already have run real graph work (the manifest
            # lookup); the count rides on the exception so it is never lost.
            graph_queries += getattr(exc, "graph_queries", 0)
            literal_scan_failed = True
            continue
        graph_queries += found["graph_queries"]
        for hit in found["results"]:
            node = dict(hit["node"])
            node.update(
                {
                    "score": 0.9,
                    "score_meaning": "exact literal match in retained snapshot source",
                    "uncertainty": "Literal text match; semantics are unverified.",
                    "match": {
                        "line": hit["line"],
                        "column": hit["column"],
                        "end_column": hit["end_column"],
                        "snippet": hit["snippet"],
                        "snippet_column": hit["snippet_column"],
                    },
                }
            )
            existing = results.get(node["id"])
            if existing is None:
                results[node["id"]] = node
            else:
                existing.setdefault("match", node["match"])
                if existing["score"] < node["score"]:
                    existing["score"] = node["score"]
    ranked = sorted(results.values(), key=lambda r: (-r["score"], r["id"]))[:12]
    overview = intent == "overview" or (
        not results
        and intent == "lookup"
        and len(question.split()) >= 4
        and not re.search(r"[`/]|\b\w+\.\w+\b|\b\w+_\w+\b", question)
    )
    if overview:
        sample = store.context_files(repo.graph_name)
        graph_queries += 1
        ranked = list({n["id"]: n for n in [*ranked[:4], *sample]}.values())[:12]
        results = {n["id"]: n for n in ranked}
    queue, visited = list(ranked[:2]), set()
    relation = "CALLS" if intent in {"dependency", "impact"} else None
    for _ in range(0 if overview else 2):
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
    results = (
        list(results.values())
        if overview
        else sorted(results.values(), key=lambda r: (-r["score"], r["id"]))[:20]
    )
    ids = {n["id"] for n in results}
    edges = [e for e in edges.values() if e["source"] in ids and e["target"] in ids]
    return {
        "results": results,
        "relationships": edges,
        "branch": repo.branch,
        "commit": repo.commit_sha,
        "warnings": ["Dynamic dispatch and external packages are not resolved."]
        + (
            [
                "Literal content scan was unavailable for this snapshot; quoted phrases may be unresolved."
            ]
            if literal_scan_failed
            else []
        )
        + (
            [
                "Repository context is a sample of indexed files, not a complete code review or test run."
            ]
            if overview
            else []
        )
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
            "literal_terms": len(literals),
            "literal_scan_failed": literal_scan_failed,
            "strategy": "repository_context" if overview else "symbol_search",
            "used_previous_question": follow_up,
            "returned_nodes": len(results),
            "context_bytes": len(str(results).encode()),
            "ranking": "1.0 exact identifier/path; 0.95 SHA prefix; 0.8 name prefix; 0.55 name/path/status; 0.4 metadata text; 0.35 direct or 0.25 second-hop neighbor; 0.2 repository context sample. Scores measure relevance, not certainty.",
        },
    }
