# Research observations and reproduction

These are research scripts, not application changes or release tests. Recorded JSON files one directory above capture the observed working tree and fixtures on 18 October 2026. See `EVIDENCE.json` for scope/model/timing and `self-analysis.json` for the 81 analyzed source hashes.

Run from the GraphPilot repository root using the existing `.venv`, for example:

```bash
PYTHONPATH=. .venv/bin/python docs/research/2026-10-18-competitive-research/probes/local-probes.py
```

As executed during research, scripts write outputs under `/tmp/graphpilot-research-20261018/`; they do not overwrite the recorded JSONs in this documentation directory. Create that directory first if reproducing elsewhere. The embedded graph probes require the installed development dependency FalkorDBLite and its local embedded binary. They create disposable UNIX-socket-only instances with `port=0`, delete only their named research graphs and close their instance in `finally`. They never import the test fixture that clears `graphpilot_test`, connect to application PostgreSQL, or use application graph credentials.

| Script | Establishes | Does not establish |
|---|---|---|
| `local-probes.py` | Small static-binding/language/intent counterexamples | Corpus-level accuracy |
| `adversarial-probes.py` | Rebound receiver/module and invalid-relative-import targets, with abstention controls | Real-project defect frequency; fixture code is parsed, not executed |
| `self-analysis.py` | File/line/node/edge/resolution counts and hashes of the analyzed working-tree source | Call-target precision/recall or API performance |
| `graph-probes.py` | Actual current search hits/plans and silent impact cap in isolated FalkorDBLite | Competitor quality or production scalability |
| `correctness-probes.py` | Citation range/flag behavior through the real context route with mocked dependencies; actual graph cap-induced distance misclassification | Full API/auth integration; route persistence and synthesis are mocked |
| `search-index-probe.py` | Exact literal candidate recovery in SQLite FTS5; synthetic equality/substring timings | Decision to add SQLite, general semantic equivalence, API latency |
| `fulltext-check.py` | Successful full-text queries with readiness evidence and explicit normalized terms | Retained-snapshot index memory/cost, raw-name camel/snake subtoken support |
| `traversal-contract-check.py` | Abstract capped traversal distances agree with independent Floyd–Warshall on all four-node simple directed graphs, across three caps | GraphPilot implementation, FalkorDB behavior, parallel-edge/work budgets or a general formal proof |

The first FalkorDB full-text subtest in `search-index-probe.py` did not check asynchronous readiness. Its zero hits are **inconclusive**, not evidence that full-text indexing fails. The recorded JSON is annotated accordingly; `fulltext-check.py` provides the readiness-checked follow-up. Identifier partial matches in that follow-up depend on the explicit `terms` property.

`availability-probe.json` records a one-off unauthenticated HTTP observation. The original inline probe is not retained as a script. It establishes those response codes at that moment, not an uptime rate or a root cause. No UI browser inspection succeeded.

`design-edge-checks.json` records an additional inline standard-library check: `read_text().splitlines()` rewrites a CRLF/U+2028 fixture, a trailing-newline count formula overcounts the last line, and `importlib.util.resolve_name` rejects the immediate beyond-package relative-import boundary. It supports the corrections in `DESIGN_NOTES.md`; it is not an application integration test. The original inline command is not retained as a standalone script.

Outputs will change after implementation. Reproduce from an appropriate source state or compare the recorded hashes before treating a changed result as a regression. Research fixtures intentionally capture failures; the implementation chat should convert relevant cases into meaningful maintained regression tests with correct expected behavior.
