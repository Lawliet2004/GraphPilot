"""Provider-independent literal search over the pinned snapshot's approved files.

The scan set is the File manifest recorded in the immutable graph — never the
mutable ``SourceFile`` head cache, a checkout root, staging, logs, Git metadata
or arbitrary disk paths. Every served byte comes from the retained snapshot
tree via the descriptor-walked reader in ``source_ranges``, and served content
is hash-verified against the manifest's ``content_hash`` before matching, so a
missing, oversized or corrupted file is disclosed as skipped rather than
silently masquerading as a completed scan.

Line and column conventions follow the shared reader: lines are delimited by
LF only (CR/CRLF/U+2028 stay inside a line, matching parser positions), columns
are 1-based character offsets into the decoded line, and long lines are served
as bounded match-anchored snippets with explicit partial markers instead of an
unbounded payload. ``column`` is inclusive and ``end_column`` exclusive — a
match at ``column`` covers ``line[column-1 : end_column-1]``.
"""

import hashlib
import time

from api.config import settings
from api.graph import store
from api.ingestion.sources import SourceError
from api.services.permissions import indexed
from api.services.source_ranges import read_snapshot_bytes, snapshot_root

QUERY_MAX = 200
RESULT_LIMIT = 50
MATCH_LIMIT = 200  # matches collected before the scan stops
FILE_LIMIT = 2000  # manifest entries examined
BYTE_BUDGET = 20_000_000  # total bytes read per search
TIME_BUDGET_MS = 1500
SNIPPET_RADIUS = 80  # context chars kept on each side of a match
SNIPPET_LINE_MAX = 240  # whole lines longer than this are served as snippets

_MANIFEST_QUERY = "MATCH (n:File) RETURN n ORDER BY n.path LIMIT $limit"


def validate_filters(path_prefix=None, suffix=None):
    """Shared typed validation for the optional path/suffix filters.

    Used identically by the HTTP route and the MCP tool so both surfaces
    accept exactly the same safe filter schema. Raises ``SourceError`` with a
    public, constant message on any unsafe value.
    """
    if path_prefix is not None:
        if len(path_prefix) > 500 or any(
            part in {"", ".", ".."} or "\\" in part
            for part in path_prefix.strip("/").split("/")
        ):
            raise SourceError("path must be a safe repository prefix")
    if suffix is not None and (
        len(suffix) > 20 or "/" in suffix or "\\" in suffix or not suffix.lstrip(".")
    ):
        raise SourceError("suffix must be a file suffix such as .py")
    return (
        path_prefix.strip("/") if path_prefix else None,
        suffix,
    )


def validate_query(query):
    """Shared literal validation — a bounded single-line string, raw."""
    if not isinstance(query, str) or not 1 <= len(query) <= QUERY_MAX:
        raise SourceError("q must be 1-200 characters")
    if "\n" in query or "\r" in query:
        # Line semantics are LF-only; a multi-line literal cannot be matched
        # honestly by a per-line scan, so it is rejected rather than returning
        # an exhaustive-looking empty result.
        raise SourceError("Multi-line literals are not supported")
    return query


def file_manifest(graph_name, limit=FILE_LIMIT):
    """Approved source files in the pinned graph, in deterministic order.

    Returns ``(rows, queries, capped)``: ``queries`` counts the actual
    ``store.query`` call so route diagnostics stay honest.
    """
    rows = [
        store.encode_node(row[0])
        for row in store.query(graph_name, _MANIFEST_QUERY, {"limit": limit + 1})
    ]
    return rows[:limit], 1, len(rows) > limit


def _folded_index(line):
    """Casefold a line while keeping a folded-offset -> original-offset map."""
    folded, index = [], []
    for position, char in enumerate(line):
        piece = char.casefold()
        folded.append(piece)
        index.extend([position] * len(piece))
    return "".join(folded), index


def _line_matches(line, needle, case_sensitive):
    """Yield ``(column, end_column)`` 1-based char spans for literal matches.

    Plain substring semantics — no word-boundary rules. Under case-insensitive
    matching a Unicode casefold expansion (for example ß -> ss) can surface
    several folded positions that map back to the same original source span;
    identical spans are deduplicated so one source range is reported once.
    """
    seen = set()
    if not case_sensitive:
        folded, index = _folded_index(line)
        needle = needle.casefold()
        position = folded.find(needle)
        while position >= 0:
            start = index[position]
            end = index[min(position + len(needle) - 1, len(index) - 1)] + 1
            if (start, end) not in seen:
                seen.add((start, end))
                yield start + 1, end + 1
            position = folded.find(needle, position + 1)
        return
    position = line.find(needle)
    while position >= 0:
        span = (position + 1, position + len(needle) + 1)
        if span not in seen:
            seen.add(span)
            yield span
        position = line.find(needle, position + 1)


def _snippet(line, column, end_column):
    """A bounded match-anchored excerpt of ``line`` with explicit cut flags."""
    if len(line) <= SNIPPET_LINE_MAX:
        return line, 1, False, False
    start = max(0, column - 1 - SNIPPET_RADIUS)
    end = min(len(line), end_column - 1 + SNIPPET_RADIUS)
    return line[start:end], start + 1, start > 0, end < len(line)


def search_source(
    repo,
    query,
    *,
    case_sensitive=True,
    limit=RESULT_LIMIT,
    path_prefix=None,
    suffix=None,
    now=None,
):
    """Scan the pinned snapshot's approved files for a literal string.

    Budgets are checked during the scan — file count, per-file and total
    bytes, elapsed time and collected matches — and every cap reached is
    disclosed through ``truncated``/``completion_reason`` with ``total`` null
    unless the scan provably finished the whole manifest.
    """
    graph = indexed(repo)
    query = validate_query(query)
    path_prefix, suffix = validate_filters(path_prefix, suffix)
    clock = now or time.perf_counter
    started = clock()

    try:
        rows, queries, manifest_capped = file_manifest(graph)
    except SourceError as exc:
        exc.graph_queries = getattr(exc, "graph_queries", 0) + 1
        raise
    advertised = (repo.stats or {}).get("files")
    manifest_incomplete = manifest_capped or (
        isinstance(advertised, int) and advertised != len(rows)
    )
    if path_prefix:
        rows = [r for r in rows if (r.get("path") or "").startswith(path_prefix)]
    if suffix:
        rows = [
            r for r in rows if (r.get("path") or "").lower().endswith(suffix.lower())
        ]

    try:
        root = snapshot_root(repo)
    except SourceError as exc:
        # The manifest query already ran — callers counting real graph work
        # must not lose it when the snapshot store is unavailable.
        exc.graph_queries = queries
        raise
    results, discovered = [], 0
    scanned_files = scanned_bytes = skipped = 0
    skip_reasons = {}
    stop = None
    for node in rows:
        path = node.get("path")
        node_id = node.get("id")
        if stop:
            break
        if scanned_files >= FILE_LIMIT:
            stop = "files_cap"
            break
        if (clock() - started) * 1000 > TIME_BUDGET_MS:
            stop = "time_budget"
            break
        if scanned_bytes >= BYTE_BUDGET:
            stop = "bytes_cap"
            break
        scanned_files += 1
        reason = None
        # Every attempted byte consumes the shared budget — including the
        # sentinel read on an oversized file and work on a file that fails to
        # open — so failed reads cannot bypass the cap. Each read is bounded
        # by both the per-file cap and the remaining total budget.
        remaining = BYTE_BUDGET - scanned_bytes
        if remaining <= 1:
            stop = "bytes_cap"
            break
        bound = min(settings().max_file_bytes, remaining - 1)
        try:
            raw, oversized = read_snapshot_bytes(root, path, bound)
            scanned_bytes += bound + 1 if oversized else len(raw)
            if oversized:
                reason = "oversized"
            elif hashlib.sha256(raw).hexdigest() != node.get("content_hash"):
                reason = "hash_mismatch"
        except SourceError:
            scanned_bytes += bound + 1
            reason = "unavailable"
        if reason:
            skipped += 1
            skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
            continue
        text = raw.decode("utf-8")
        lines = text.split("\n")
        if text.endswith("\n"):
            lines.pop()  # trailing LF belongs to the last line
        for lineno, line in enumerate(lines, 1):
            if (clock() - started) * 1000 > TIME_BUDGET_MS:
                stop = "time_budget"
                break
            for column, end_column in _line_matches(line, query, case_sensitive):
                discovered += 1
                if len(results) < limit:
                    snippet, snippet_column, start_cut, end_cut = _snippet(
                        line, column, end_column
                    )
                    results.append(
                        {
                            "node_id": node_id,
                            "node": node,
                            "path": path,
                            "line": lineno,
                            "column": column,
                            "end_column": end_column,
                            "snippet": snippet,
                            "snippet_column": snippet_column,
                            "snippet_start_partial": start_cut,
                            "snippet_end_partial": end_cut,
                            "line_length": len(line),
                            "content_hash": node.get("content_hash"),
                        }
                    )
                if discovered >= MATCH_LIMIT:
                    stop = "matches_cap"
                    break
                # A long line can yield many matches; the deadline must be
                # checked during match work, not only between lines/files.
                if (clock() - started) * 1000 > TIME_BUDGET_MS:
                    stop = "time_budget"
                    break
            if stop:
                break
            # Zero-hit lines still consumed real work (decode/casefold);
            # re-check the deadline after each line, not just before it.
            if (clock() - started) * 1000 > TIME_BUDGET_MS:
                stop = "time_budget"
                break
    if stop is None:
        stop = "files_unavailable" if skipped else "exhausted"
    # ``scan_complete`` reports the scan itself covering the whole approved
    # manifest; ``truncated`` additionally covers a response cut by the result
    # cap, so a result-capped answer on a finished scan is still disclosed.
    scan_complete = stop == "exhausted" and not manifest_incomplete and not skipped
    response_cut = discovered > len(results)
    truncated = not scan_complete or response_cut
    if stop != "exhausted":
        reason = stop
    elif manifest_capped:
        reason = "manifest_cap"
    elif manifest_incomplete:
        reason = "manifest_mismatch"
    elif skipped:
        reason = "files_unavailable"
    elif response_cut:
        reason = "result_limit"
    else:
        reason = "exhausted"
    return {
        "results": results,
        "returned": len(results),
        "limit": limit,
        "total": discovered if scan_complete else None,
        "scan_complete": scan_complete,
        "truncated": truncated,
        "has_more": truncated,
        "completion_reason": reason,
        "scan": {
            "files_scanned": scanned_files,
            "files_skipped": skipped,
            "skip_reasons": skip_reasons,
            "bytes_scanned": scanned_bytes,
            "elapsed_ms": int((clock() - started) * 1000),
            "manifest_entries": len(rows),
            "manifest_incomplete": manifest_incomplete,
        },
        "graph_queries": queries,
        "scope": {
            "branch": repo.branch,
            "snapshot_id": repo.snapshot_id,
            "commit": repo.commit_sha,
            "historical": repo.historical,
            "manifest": "File nodes in the pinned graph only",
            "case_sensitive": case_sensitive,
            "filters": {"path": path_prefix, "suffix": suffix},
        },
    }
