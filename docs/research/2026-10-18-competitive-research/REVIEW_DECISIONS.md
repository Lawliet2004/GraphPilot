# Decisions after critical review

SWE-2 Max researched commercial products and source implementations, then performed separate commercial, source and feasibility reviews. The supervising agent checked load-bearing claims against primary documentation/source and ran isolated probes. This records evidence-based decisions and corrections, not private internal reasoning transcripts.

| Proposed claim or direction | Decision | Reason / evidence |
|---|---|---|
| Current symbol search is sufficient code search | Reject | Four ordinary literals exist in source but return zero graph metadata hits; `graph-probes.json` |
| A new text index must precede useful content search | Revise | Approved snapshot bytes already exist; begin with a bounded, disclosed scan, then choose an index from corpus/latency data |
| Impact cap is only a missing warning | Reject | `correctness-probes.json` reproduces a direct caller labeled indirect due to pre-dedup path cap |
| Existing citations already preserve exact returned ranges | Reject | Real context route fixture returns 75 lines but claims 200 and omits truncation metadata |
| More resolved calls automatically means better analysis | Reject | Adversarial rebinding/relative-import fixtures emit wrong targets; measure false links and abstention separately |
| Graph is rebuilt on every retrieval | Reject | Graph publication happens during indexing; retrieval queries the persisted snapshot graph |
| Existing exact-name score uses an indexed lookup | Reject | Exact scoring is inside a substring-query tier. The equality lookup spike is a proposed fast path, not current name-query behavior |
| Full-text indexes solve all literal/identifier retrieval | Reject | Source bodies remain separate; normalized terms are needed for the tested subtoken matches; short-query behavior differs by backend |
| Current Cursor code search requires stored code embeddings | Reject as stale | Canonical current Search docs describe local Instant Grep and state codebase embeddings are not stored for search |
| Sourcebot's public MIT file licenses an inspectable application runtime | Reject | Pinned public tree contains configuration/deployment/schema tooling; runtime image rights cannot be inferred |
| GitNexus permits unrestricted commercial code reuse | Reject | Pinned license is PolyForm Noncommercial; study its concepts without assuming unrestricted reuse |
| Serena has one blanket license for every component | Reject | Application GPL and SolidLSP MIT licensing require component-level treatment |
| JS/TS parsing implies verified call targets | Reject | Definitions, source occurrences, reference resolution and call targets need separate precision tiers and evaluations |
| `SourceFile` can supply retained-snapshot occurrence truth | Reject | It is a mutable branch/path head cache; use immutable snapshot/tree + path + hash |
| All snapshot comparison has the same identity difficulty | Revise | IDs exclude commit but include branch; same-branch diff is the cheaper first slice, cross-branch/rename matching later |
| Existing TESTS edges prove runtime coverage | Reject | Current rule records resolved direct calls from `test_`-prefixed functions; transitive paths and imported runtime coverage are separate |
| History metadata is authoritative for renames/deletions | Reject | Previous filename is not retained; records can survive upstream failures/404s; compare exact source snapshots for diff truth |
| Owner-led team sharing is already supported | Reject | Grant/revoke is global-admin-only; add owner-authorized membership workflow or retain explicit single-user scope |
| GitHub index-time access checks equal live host ACL sync | Reject | Read access is current application membership; no member-host mapping or sync policy exists |
| Uploaded SCIP with matching hashes is verified analysis | Reject | Hashes validate source alignment; uploader/tool provenance and analysis trust are separate, and references are not automatically CALLS |
| Broad embeddings/wiki/cross-repo work is the best first investment | Defer | Demonstrated evidence/correctness gaps block ordinary tasks; add broader features after measured relevance and user demand |

The full report gives primary links, tradeoffs and acceptance criteria. `IMPLEMENTATION_HANDOFF.md` translates the accepted priorities into an initial release and dependent follow-on slices. The final SWE-2 Max design review was reconciled in [DESIGN_NOTES.md](DESIGN_NOTES.md), including independent counterchecks correcting its newline formula, relative-import boundary, scanner query accounting and byte-read/path-guard advice.
