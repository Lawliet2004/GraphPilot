# Source evidence implementation — 18 October 2026

The first coherent release in the [research handoff](../../research/2026-10-18-competitive-research/IMPLEMENTATION_HANDOFF.md) is implemented locally: bounded literal discovery → exact retained source → caller trace or source-pinned Ask. Python binding, shortest-distance impact, citation fidelity and question-routing defects were also corrected. The larger research roadmap remains follow-on work.

Implementation used Devin CLI **SWE-2 Max**, with Codex independently reviewing the patch and exercising counterexamples. No project changes were committed, pushed, deployed or published. Existing dirty work and research artifacts were preserved.

## Delivered behavior

- **Code:** choose Symbols or Content; Content searches literal text with an explicit Match case control. Results show path, line, character column and a bounded snippet. Open a result with the keyboard to inspect the actual matching source, including matches after line 200. Scan coverage and partial-result notices appear beside results; symbol search and the Ask/Code/Activity tabs remain available.
- **Ask:** a result can pin the exact source selection and immutable snapshot. The served excerpt contains the match even when it is deep into a long line. Citations retain source hashes, served line ranges, partial-line/window flags and upstream truncation when saved. Deterministic retrieval works without a model key; synthesis remains optional per-user BYOK.
- **HTTP and read-only MCP:** shared literal-search and bounded source-range services, with current token/membership checks and immutable branch/snapshot/commit provenance. MCP adds `search_content` and `read_source`; repository discovery supports filtering/pagination and returns snapshot handles. Legacy HTTP repository-list callers retain their array response when pagination is omitted.
- **Python semantics:** rebinding `self`/`cls`, replacing module definitions and escaping relative imports no longer preserve the demonstrated false targets. Valid controls remain resolved. Parser version is `python-ast-4`; CR-only Python files explicitly abstain from semantic extraction rather than publish misleading line positions.
- **Impact:** incoming one-hop traversal completes shallower layers before deeper ones, retaining shortest directed witnesses. Cycles and duplicates are bounded. Results disclose limits, incomplete traversal, known totals and actual graph-query counts.
- **Routing:** payment failure alone no longer routes to CI. Meaningful workflow context still routes valid CI tasks; quoted literals and explicit file locations remain data.

## Contracts and limits

Content queries are **1–200 characters, single-line literals**, with safe path-prefix and suffix filters. Punctuation, quotes, raw surrounding whitespace and one/two-character Unicode strings are supported. Case-insensitive matching uses Unicode casefolding and maps back to original character spans. Columns are 1-based, inclusive start/exclusive end; LF delimits lines, with CRLF preserved in served text.

The scanner reads only File entries approved in the selected immutable graph and hash-verifies retained bytes. It does not use mutable head-cache rows or scan working trees. Descriptor-relative reads reject symlinks through snapshot ancestors and leaf paths. Existing storage read locks protect reads against concurrent retirement. Missing, corrupt or oversized files produce partial coverage rather than an exhaustive-looking zero.

| Operation | Bounds and disclosure |
|---|---|
| Literal scan | 2,000 manifest entries; 20,000,000 attempted bytes; existing ingestion per-file limit; cooperative 1,500 ms scan deadline; 200 collected matches; at most 50 returned |
| Source read | At most 200 lines / 12,000 characters; match-anchored column windows for long lines; exact hash/range and partial metadata |
| Ask evidence | At most 8 citations / 24,000 characters, at most 3,000 characters each; the real remaining budget is passed before selecting a match window |
| Impact | Default 100 results; 1,000 edges per layer plus sentinel, 20,000 total edge budget, 8 internal graph queries, cooperative 9,000 ms deadline and existing 3,000 ms graph-query timeout |

`scan_complete` distinguishes coverage from a response cut by its result limit. `truncated`, `has_more`, `completion_reason`, skip reasons and scope are additive; exact search totals are emitted only after a complete scan. Impact separately reports traversal completeness. Reported query counts include failed attempts and wrapper lookups.

## Independent verification

Tests ran against disposable PostgreSQL/FalkorDB services on dedicated loopback ports, with separate test and browser databases and a separate retained-source root. Existing demo services were untouched. Temporary API/worker/Vite processes and the two owned test containers were stopped after verification; baseline backups, probe scripts and evidence remain available. Repository ingestion did not execute fixture source code.

| Parent-run check | Result |
|---|---|
| Full backend suite | **280 passed, 1 skipped**, 38.08 s |
| Ruff + TypeScript (`make lint`) | Passed |
| App tests | **6/6 passed** |
| Production build (`make build`) | Passed |
| Full maintained Playwright suite | **8/8 passed**, 1.6 min, fresh disposable browser database |
| Additional independent browser probe | **1 passed**: exact source, caller, pinned Ask, keyboard/focus, whitespace, desktop/mobile, actual empty and partial states |
| Dirty-tree whitespace check | Passed |

The skipped backend check requires the Firebase auth emulator; one existing Starlette TestClient deprecation warning remains. Browser evidence is from real Chromium through Playwright. CUA was unavailable because its browser policy failed to load. These checks do not certify all routes, all accessibility criteria, or production readiness.

Parent counterexamples went beyond the implementation agent's tests:

- Twelve binding cases plus import-alias ordering; valid direct/self/relative-import controls alongside replacement, deletion, conditional/walrus and package-escape cases.
- 160 seeded directed graphs against independent shortest distances, cycles/parallel edges, both saturated insertion orders, 105 direct callers, depth/cap handling and timeout query accounting.
- Eight citation-fidelity cases covering CRLF, Unicode separators, partial/empty text, old unknown truncation, non-source ranges and saved-response equality.
- Twenty real HTTP/MCP integration checks: the four research misses (`X-CSRF-Token`, `Request origin is not allowed`, `python-ast-3`, `graph_queries`) at lines 232–235; short/quoted/Unicode/case/whitespace literals; approved-manifest exclusions; retained-source stability after reindexing; a match beyond a 20 KB line prefix; current membership/token revocation and retired-snapshot failure.
- Snapshot-prefix and repository symlink rejection; retained-byte tampering returns HTTP 409 without serving modified content under the old hash; attempted-byte/deadline bounds; casefold span deduplication; honest multiline rejection and known-total response truncation.
- Fifty-five visible repositories paginate 20/20/15 without duplicates; an owner row without membership stays hidden. Actual graph-call counts match diagnostics, including failed scans. An exclusive storage lock fails during the read and succeeds afterwards.

The initial full browser run passed 5/8. The remaining failures were demonstrated preexisting harness issues: stale CLI consent wording, ambiguous developer-tools labels, and a hardcoded admin request origin. The relevant app/test files were byte-identical to the captured baseline before repair. SWE-2 Max updated only those harness expectations/selectors/configuration; meaningful assertions remain. Repeated sign-ins then hit the disposable environment's normal rate limit, so confirmation used a cooldown rather than weakening authentication. The repaired cases then passed together. A subsequent full run passed 6/8 but exposed another preexisting harness dependency: Developer tools left its GitHub indexing job running on the shared serial worker, delaying both journeys. All jobs ultimately succeeded; both journeys passed with the queue clear (44.3 s / 9.4 s). A bounded readiness assertion now drains that test’s own indexing job before exit. No application behavior or assertion was weakened. The next run passed 7/8; the last signup reached the shared database’s durable rate limit from accumulated runs. Final confirmation therefore uses a fresh disposable browser database, with the same authentication rules. The final complete run passed **8/8 in 1.6 minutes**. All outcomes are retained in VERIFICATION.json.

## Provenance and preservation

[VERIFICATION.json](VERIFICATION.json) records model selectors/session export hashes, checks, independent receipts, changed paths, preservation and visual-review scope. Full private CLI exports remain outside the repository; no internal reasoning transcript or fixture credential is copied into this report.

- Exact implementation selector: `swe-2-max`; exported `agent.model_name`: `SWE-2 Max`; CLI `3000.11.92`; resumed implementation session `mangrove-deposit` for batches A–E.
- Baseline HEAD: `765644ced40dbb6ac82943a7a8c4ac78891dad0b`, unchanged. A patch, untracked archive and 273-file SHA-256 inventory were captured before edits under `/tmp/graphpilot-implementation/baseline-20261018T091420Z`.
- No baseline files were deleted. All 29 dated research files remain byte-identical. Source changes are additive to the captured working tree; unrelated existing modifications remain intact.
- The [fresh finish reviewer](finish-review-result.md) returned **ship** for the six [captured views](screenshots/source-content-desktop.png), with no material extension regressions. Non-blocking residuals are singular/plural copy, mechanical cap wording and incumbent compact 10px source type. The [ordinary-extension documenter](documenter-check-result.md) found no system drift or required token changes; DESIGN.md has a minor feature-log gap. Existing design direction provenance is preserved; this work does not imply user approval of a new direction.

Maintained regressions are in [test_content_search.py](../../../tests/test_content_search.py), [test_correctness_contracts.py](../../../tests/test_correctness_contracts.py), and [content-evidence.spec.ts](../../../e2e/content-evidence.spec.ts), alongside existing affected suites. Parent probe scripts, raw logs and captures remain under `/tmp/graphpilot-implementation`; the durable verification record contains sanitized receipts.

## Remaining limitations and next runnable slice

- This is a bounded scan, not a durable lexical index. The manifest cap is applied **before** optional path/suffix filtering; a target late in a large snapshot may remain outside coverage. Deadlines are cooperative, not hard CPU preemption. Result notices must remain visible.
- Approved ingestion policy determines searchable files. This release does not add a universal secret detector or blanket dotfile exclusion; an approved `.env` can be searchable. Git-ignored, stray and symlinked files in the verification fixture were excluded according to their actual policy/manifest status.
- Python analysis remains conservative static analysis, not runtime proof. Existing retained graphs are not rewritten; **reindex to obtain `python-ast-4` semantics**. Some preexisting runtime/name-order approximations remain. Old saved citations without completeness fields retain unknown completeness.
- No raw regex/multiline search, new language extraction, embeddings, cross-repository inference, durable context-bundle export, snapshot comparison or team-membership workflow was added.

Next: implement the **JS/TS/TSX definition tier** from the handoff: common extractor IR; pinned packaged grammars; bounded workers; honest generic Symbol + `symbol_kind` for interfaces/type aliases; exact ranges, filters/stats, coverage and cache versioning. Start with a fixture matrix and timeout/resource boundary, then use the app's source as a demonstration corpus. Do not guess call edges. Grammar availability was checked only; no grammar dependency was installed and no language support is claimed here.
