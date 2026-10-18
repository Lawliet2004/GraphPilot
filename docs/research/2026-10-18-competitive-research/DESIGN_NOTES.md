# Verified design notes for implementation

These are the supervising agent's accepted conclusions and corrections after SWE-2 Max's final implementation-design review. The raw review is a lead, not an implementation specification. Use these notes with the handoff and report.

## Approved source scope and lifecycle

`read_files()` selects bounded UTF-8 text; `prune_snapshot()` removes nonselected files before the source tree is published. `build_graph()` creates one File node per selected path with its content hash. The **pinned graph's File set** is therefore an available immutable approved-path manifest; `SourceFile` rows remain mutable head caches. A bounded manifest query can avoid scanning stray future artifacts under the source directory. Check manifest completeness against the advertised file count and disclose corruption/missing files.

This scope includes approved non-code text and dotfiles; current ingestion is not a blanket secret detector. Search must preserve the existing source/exclusion/access boundary and must not advertise that every retained file is secret-free. Never scan staging, uploads, logs, live checkout roots or unrelated disk paths as source.

`repository_access()` acquires a transaction-scoped shared advisory storage lock before resolving the repository. Keep graph-manifest lookup and file reads within that transaction; a commit releases the lock. HTTP dependency scope and MCP `SessionLocal` scope already provide the useful pattern. Read-only scanner/range handlers must not commit mid-read. Deletion/retention must not remove a source tree still being served. Reuse these protections and test the race rather than adding a second lock scheme.

Do not copy the old path guard mechanically: calling `is_symlink()` **after** `resolve()` no longer tests the submitted symlink. Reject unsafe components/symlinks before following them, validate the owned root/path, and consider descriptor-based no-follow reads where appropriate. `Path.read_bytes()` also reads the whole file; a stated byte cap requires bounded reads (for example `read(cap + 1)`) and a cap check, not just checking length afterward. Owned immutable storage reduces races but does not make these APIs equivalent.

## Traversal completeness

Use incoming one-hop expansion and complete shallower layers before claiming a deeper shortest distance. If an origin/edge/work cap interrupts a layer, stop deeper exploration or explicitly label later paths provisional. Preserve a directed witness path and avoid re-expanding visited nodes. Existing graph read timeouts are 3,000 ms per query; also bound total queries/work. Exact direct totals remain null when not established.

The abstract model check supports these small-graph cap semantics, not database execution or resource claims. The built-in BFS interface must not be assumed to support incoming multi-type traversal or internal work limits. Test any chosen query on the installed FalkorDB version. `ORDER BY` and aggregation can perform substantial work before a final LIMIT; a short returned list is not proof of bounded execution.

## Source ranges and evidence

Define line/column and partial-line semantics before changing the reader. Read raw bounded bytes and decode strict UTF-8 when byte fidelity matters. Current `read_text()` normalizes CRLF, and `splitlines()` additionally splits on Unicode separators such as U+2028. Switching to an LF-only range reader therefore changes **CRLF output as well as exotic separators**, and is not byte-identical to the current route. Pin expected normal/CRLF/Unicode behavior with known source positions and describe the compatibility change.

Reject the review's unconditional `end_line = start + content.count("\n")`: `"line1\nline2\n"` would incorrectly report line 3. Prefer whole-line packing where possible, define how a trailing delimiter belongs to its preceding line, and handle a long first-line partial cut explicitly. An empty served excerpt is not automatically `truncated=false` when a nonempty selected span or upstream truncation exists. Preserve non-source evidence's null source ranges rather than fabricating file positions.

The current LogArtifact boundary check uses **characters**, not bytes. It already flags input longer than 12,000 because the sliced excerpt has length 12,000; the defect is also flagging exactly 12,000. Compare original length to the cap if fixing it. This small boundary issue is lower priority than the reproduced source/context range bug.

Apply context padding in one place. Do not subtract/add three lines in the caller and then have a range helper apply another three. A hit after line 200 must open a range containing the match and feed that same pinned range into Ask, rather than linking only the File node's first excerpt.

New evidence fields must be optional for older saved JSON/TypeScript clients. Missing old truncation metadata means unknown, not a newly proven complete excerpt. Thread **both branch and snapshot revision** for nondefault branches: the current resolver validates the snapshot against the selected branch. Preserve that contract initially instead of silently changing branch inference.

## Diagnostics and static binding corrections

A file scan can use `source_scans`, but a graph-backed manifest lookup **does issue Cypher**. Count every actual `store.query()` call in `graph_queries`, including scanner/range manifest lookups, rather than following the review's claim that the scanner issues none. Keep the existing diagnostics invariant and adjust the declared maximum for the designed bounded operation count.

Do not blindly apply the review's relative-import threshold `level > len(package) + 1`. Standard-library `importlib.util.resolve_name("..target", "pkg")` raises ImportError, while `.target` in `pkg` and `..target` in `pkg.sub` resolve. Include that immediate beyond-top-level boundary and `__init__.py` package identity in fixtures; do not infer correctness from the single reproduced three-dot example. Record unsupported cases conservatively. The supervising agent independently checked these standard-library cases, CRLF/U+2028 rewriting, and trailing-newline counting in [design-edge-checks.json](design-edge-checks.json).

After a parser-version bump, `python-ast-3` may intentionally disappear from current parser source. Literal-search regression tests should use the pinned baseline or explicit fixture text containing the four recorded strings, rather than assuming the current application's version literal never changes. Preserve old snapshots' bytes and invalidate only the intended new-generation parse artifacts.

## Scope and verification

The design review estimates that correctness + scanner + HTTP + MCP + web integration can exceed the suggested 2–3 hours. Treat that as an estimate, not a reason to weaken release gates or stop at an invisible prototype. Implement dependency-ordered batches, verify each, and finish the coherent first workflow before expanding into definitions/context/diffs. Report remaining work honestly. No exact duration is guaranteed.

Relevant repository commands are `uv run pytest -q ...`, `make lint`, `npm --prefix app test`, `make build` and the configured Playwright journeys. Inspect fixture configuration first: the pytest fixture creates/migrates and truncates `graphpilot_test`; use isolated test services and avoid concurrent users of that fixture database. Run only the appropriate checks during batches and broaden once for the final changed scope. Browser failure is a recorded verification limitation, not a passing UI check.
