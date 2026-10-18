# Research-to-implementation handoff

The user explicitly requested a separate new chat **after research is complete**, using **SWE-2 Max through Devin CLI** as the implementation agent, with the supervising Codex agent independently reviewing and verifying the work. They suggested roughly 1–2 hours for research and 2–3 hours for implementation. This document is the concrete execution plan for that next chat. Research artifacts are complete when `EVIDENCE.json` records `research_completed_at_utc`.

Read [REPORT.md](REPORT.md), [SOURCES.md](SOURCES.md), [EVIDENCE.json](EVIDENCE.json), [DESIGN_NOTES.md](DESIGN_NOTES.md) and the probe README. The design notes include parent-verified corrections to SWE-2 Max's final review; do not blindly implement the raw review. The report is a ranked roadmap, not a promise that every language, collaboration feature and enterprise integration fits into a single afternoon. Implement the first coherent release below, verify it, then progress through the next dependencies while useful implementation time remains. State what was actually delivered and what remains; do not label the whole roadmap implemented after one slice.

## Working context and preservation

- Repository: `/home/papan/Desktop/Projects/GraphPilot`; researched HEAD `765644ced40dbb6ac82943a7a8c4ac78891dad0b` **plus substantial preexisting dirty work**.
- Product: static, evidence-aware code investigation; deterministic use without an LLM; optional per-user BYOK; no repository code execution during ingestion; current ACLs and immutable retained snapshots.
- Existing architecture: FastAPI/SQLAlchemy/PostgreSQL, FalkorDB, React/TypeScript/Vite, three repository tabs Ask/Code/Activity, authenticated read-only MCP.
- Research modified only this new dated documentation directory. Never reset/revert/overwrite the user's existing changes. Inspect the current diff and untracked files before delegating; capture a local baseline patch/hash inventory outside Git. Do not make a baseline commit without a reason. Work additively in dirty files when necessary.
- Read applicable `AGENTS.md`, `PRODUCT.md`, current handoff/design documentation and relevant skill instructions. Use the impeccable skill for interface changes, with browser verification when available.
- Do not deploy, publish, push, send external messages or change paid hosting as part of this task. The user authorized implementation and local verification. No new permission question is needed for that work.

## Required delegation and independent verification

The installed binary is `/home/papan/.local/bin/devin`, version `3000.11.92`. `devin models list` verified selector **`swe-2-max`**. Use this exact model for implementation; do not silently substitute a native Codex subagent. A working noninteractive invocation is:

```bash
devin --model swe-2-max --permission-mode dangerous --respect-workspace-trust false \
  --prompt-file /tmp/graphpilot-implementation/prompt.md \
  --export /tmp/graphpilot-implementation/session.json -p \
  > /tmp/graphpilot-implementation/cli.log 2>&1
```

This CLI mode enables tool execution; constrain the prompt to the authorized repository changes and isolated verification, with no credentials, deployment, destructive Git or messages. Research found `smart` unsupported and `accept-edits` blocked noninteractive shell access. Preserve session metadata showing `agent.model_name == "SWE-2 Max"`; extract only provenance, not internal reasoning transcripts, into the delivery record. Session export appears at completion, so an old file is not proof of a current run.

Give the agent concrete contracts and regression criteria, review its patch, run independent checks, and return failures for repair. Parent verification must exercise meaningful counterexamples beyond merely accepting the agent's test report. Maintain user updates throughout the task. Use small, dependency-ordered implementation batches to reduce overlap and make failures attributable.

## First coherent release: source evidence users can trust

### A. Fix demonstrated semantic and evidence defects

1. Conservative Python binding fixes in `api/ingestion/python.py`: `self`/`cls` rebinding, module-level replacement of a function, and relative imports escaping the package root must not retain an obsolete/unrelated verified target. Withhold and disclose unsupported cases rather than guessing. Keep controls that correctly resolve direct calls and abstain on ordinary shadowing/missing imports. Bump parser/cache version when parsed semantics change.
2. Fix impact correctness in `api/graph/store.py`. The current query enumerates paths then `LIMIT 100`, then deduplicates and selects shortest returned paths in Python. The fixture in `correctness-probes.json` **reproduces a direct caller classified distance 2**, with either direct-edge insertion order. Use bounded traversal/aggregation that preserves known shortest distances and directed caller semantics. Do not fix this by performing unbounded path enumeration or removing caps.

   A candidate is incoming one-hop frontier queries, expanding complete layers in order and stopping when an earlier layer is incomplete. The research-only `traversal-contract-check.json` compares that abstract cap behavior to independent Floyd–Warshall distances on four-node graphs; it does not validate a database implementation. Keep query/edge/work budgets and timeout handling, and avoid claiming shortest distances after skipping part of a shallower layer. Check the installed FalkorDB API before assuming built-in BFS supports direction/multiple types or internal work limits.
3. Add additive completeness metadata for impact and new search operations: returned, limit, truncated/has_more, completion reason, snapshot/analysis scope; exact totals only when known. Preserve current callers where practical. A generic dynamic-dispatch notice does not describe a capacity cap.
4. Fix context citation truncation in `api/routes/context.py` and TypeScript/rendered evidence. The real route fixture returns 3,000 characters/75 lines while claiming lines 1–200 and dropping `truncated`. Preserve upstream truncation; recompute the returned line range after slicing; indicate a partial final line if needed. Keep an exact-source read path for the omitted text. Carry metadata into saved responses, API types and UI. Do not claim citation-ID validation proves prose entailment.

### B. Bounded source-content search and matching evidence

Implement a provider-independent literal-search service over the **retained snapshot's approved source files**, initially a bounded scan. Use the existing repository-view ACL/revision gate and storage read locks. Do not scan checkout roots, Git metadata, excluded secrets, symlinks, arbitrary disk paths, or mutable `SourceFile` rows as historical truth. Determine the approved manifest from immutable snapshot state; the research design review documents the precise seam.

Define small typed inputs: literal query, optional safe path/language filter, snapshot, bounded result limit and explicit case behavior. Keep exact punctuation, quotes and short Unicode queries correct. Restrict raw regex in the first slice unless it is safely bounded. Bound files, bytes, time/work and matches; check budgets during scanning, and disclose incomplete scans. Return exact path, matching line/span, source hash or equivalent snapshot provenance, and enough context to open the hit. Order deterministically. Avoid concatenating user text into Cypher or shell commands.

The four baseline misses must be recovered: `X-CSRF-Token`, `Request origin is not allowed`, `python-ast-3`, and `graph_queries`. Add an independent fixture whose only match is **after line 200**: the existing File-node evidence excerpt reads the beginning of a file, so simply linking the File node is insufficient. Reuse or introduce a shared bounded source-range reader; a search hit and Ask citation must contain the actual match at the selected immutable snapshot.

No new database/service is required for this first scan. Durable lexical indexing follows measured corpus/latency need, with publication, retention, deletion and backup designed together. The SQLite/FalkorDB spikes are observations, not instructions to add SQLite or bulk source bodies to graph properties.

### C. Put the improvement into the existing workflow

- Add a clear literal/content search mode and matching-source action in Code/Ask, keeping the three main tabs. Preserve symbol search. Show partial/unsupported results near the result, with keyboard-accessible controls and a useful empty state.
- Fix question routing: “How is payment failure handled?” must not become CI solely due to “failure.” Require meaningful workflow context; preserve quoted literals and explicit locations. Keep existing valid CI tasks working.
- Expose the same search and bounded range-read service through authenticated read-only MCP. Thread an immutable snapshot handle from result to evidence/impact/context so a head update between calls cannot mix generations. Recheck current token and repository membership for every operation.
- Add repository discovery pagination/filtering if needed to make the new tool usable beyond the first 50 repositories; prioritize a clear complete contract over a larger raw tool count.
- Exact name/ID fast paths may be added if they preserve ranking/fallback behavior and have meaningful plan/latency checks. The current exact-name score tier is not an indexed name-query fast path.

## Acceptance and independent release gates

| Area | Required behavior |
|---|---|
| Static bindings | Adversarial false-target fixtures abstain or resolve correctly; ordinary direct-call controls remain correct; unresolved reasons/coverage remain honest |
| Impact | 105 direct callers disclose an incomplete bounded result; a direct caller with many two-hop paths cannot be mislabeled indirect; cycles, duplicates and depth limits stay bounded |
| Citation fidelity | Source line ranges describe served text; partial slices and upstream truncation remain visible; Unicode, CRLF, empty/non-source evidence and saved responses are handled |
| Literal discovery | All four reproduced misses return exact lines; one/two-character strings, punctuation, case, quotes and Unicode have defined behavior |
| Beyond initial excerpt | A match after line 200 opens and feeds context with the correct range and snapshot |
| Isolation/lifecycle | Unauthorized/revoked users and tokens cannot read search hits, counts or range content; retained snapshots stay stable after reindex; retired/deleted artifacts fail cleanly; traversal/symlinks excluded |
| Budgets | Scan file/byte/match/time bounds are enforced and reported; a stopped scan cannot masquerade as exhaustive zero matches |
| Integration | HTTP and MCP use the shared implementation and snapshot identity; valid old symbol/CI/context tasks still work; payloads remain bounded |
| Web | Literal → exact source → callers/context works in browser where available; keyboard, loading, empty and partial states checked; no unverified visual/a11y claim |

Relevant existing checks: `tests/test_indexing.py`, `test_ingestion_budgets.py`, `test_ignore_rules.py`, `test_retrieval_benchmark.py`, `test_context.py`, `test_mcp.py`, `test_revisions.py`, `test_lifecycle.py`, `test_auth.py`; `app/tests/api.test.mjs`; Playwright journeys and source/evidence paths. Inspect test configuration and use isolated fixtures, never the user's production data. Run focused tests during batches, then the repository's appropriate lint/type/build and integration/release checks for the changed scope. Record preexisting failures separately using evidence, not assumptions. Do not rerun passing broad checks repeatedly without a new change or unresolved concern.

## Next slices, after the first gates pass

1. **JS/TS/TSX definition tier:** common extractor IR, pinned packaged grammars and bounded workers; honest generic `Symbol` plus `symbol_kind` for interfaces/type aliases; whitelist, filters/stats, coverage labels, exact ranges and cache versioning. No guessed call edges. The current frontend's 20 TS/TSX files are a useful local demonstration corpus, not accuracy ground truth.
2. **Provider-independent context bundles:** exact matched spans, overlap deduplication, explicit tokenizer/estimate, omitted-evidence accounting, Markdown/JSON export and MCP. First fix range fidelity; then compare simple ranking against graph-ranked repository maps.
3. **Same-branch snapshot comparison:** IDs exclude commit, so compare ID + source fingerprints within a branch first. Exact source manifests are authoritative; stale history is context. Cross-branch/rename identity matching is later.
4. **Team use:** owner-authorized membership workflow before saved/shared investigations; no role escalation. Host ACL synchronization is a separate policy/integration decision.

Embeddings, cross-repository inference, imported SCIP, webhook ingress, generated wikis, architecture rules and broad language expansion remain ranked follow-on work unless concrete evidence makes them the next feasible dependency. Keep all delivered claims narrower than the tests and measurements that support them.

Finish with an implementation report listing changed behavior, SWE-2 Max provenance, independent verification, remaining limitations and the next runnable slice. Do not claim browser verification if unavailable, competitor superiority without comparative tests, or all 20 roadmap packages completed.
