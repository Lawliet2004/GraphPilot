# Sources and implementation catalog

Access date: **18 October 2026**. This catalog supports [REPORT.md](REPORT.md). Source inspection used shallow checkouts and commit-pinned raw files; the record does not claim that upstream software was executed or benchmarked. The main report is the reviewed synthesis.

## Repository evidence

Each SHA identifies inspected content, including the license at that revision. Licenses are recorded as facts about those files; direct reuse still needs the notices, dependencies and compatibility for the intended distribution checked. No upstream source was copied into GraphPilot during this research.

### aider

[Repository at `5dc9490bb35f9729ef2c95d00a19ccd30c26339c`](https://github.com/Aider-AI/aider/tree/5dc9490bb35f9729ef2c95d00a19ccd30c26339c) · [License: Apache-2.0](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/LICENSE.txt)

Definition/reference tags, personalized PageRank over file/name signals, and rank-then-pack repository maps. Parent and Swe2Max source inspection. Same-name ranking links should not become verified dependency facts.

Key source: [aider/repomap.py](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/repomap.py), [aider/queries/tree-sitter-language-pack](https://github.com/Aider-AI/aider/tree/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/queries/tree-sitter-language-pack).

### continue

[Repository at `5522c6f44ca0ac3528b37244818fbfa39b5af470`](https://github.com/continuedev/continue/tree/5522c6f44ca0ac3528b37244818fbfa39b5af470) · [License: Apache-2.0](https://github.com/continuedev/continue/blob/5522c6f44ca0ac3528b37244818fbfa39b5af470/LICENSE)

Artifact-specific incremental indexing and a portfolio of retrieval sources. The inspected full-text implementation uses SQLite FTS5 with trigram tokenization. Editor recency and multiuser server snapshots have different semantics.

Key source: [core/indexing/refreshIndex.ts](https://github.com/continuedev/continue/blob/5522c6f44ca0ac3528b37244818fbfa39b5af470/core/indexing/refreshIndex.ts), [core/indexing/FullTextSearchCodebaseIndex.ts](https://github.com/continuedev/continue/blob/5522c6f44ca0ac3528b37244818fbfa39b5af470/core/indexing/FullTextSearchCodebaseIndex.ts), [core/context/retrieval/pipelines/NoRerankerRetrievalPipeline.ts](https://github.com/continuedev/continue/blob/5522c6f44ca0ac3528b37244818fbfa39b5af470/core/context/retrieval/pipelines/NoRerankerRetrievalPipeline.ts).

### zoekt

[Repository at `0e68f41329d9c37f46942d4731495fa05b07882a`](https://github.com/sourcegraph/zoekt/tree/0e68f41329d9c37f46942d4731495fa05b07882a) · [License: Apache-2.0](https://github.com/sourcegraph/zoekt/blob/0e68f41329d9c37f46942d4731495fa05b07882a/LICENSE)

Positional trigrams, candidate verification, and structured match scoring. Parent re-fetched commit-pinned design and scoring sources after initial clone failures. Its documented performance goals are not measurements reproduced here.

Key source: [doc/design.md](https://github.com/sourcegraph/zoekt/blob/0e68f41329d9c37f46942d4731495fa05b07882a/doc/design.md), [index/score.go](https://github.com/sourcegraph/zoekt/blob/0e68f41329d9c37f46942d4731495fa05b07882a/index/score.go), [index/contentprovider.go](https://github.com/sourcegraph/zoekt/blob/0e68f41329d9c37f46942d4731495fa05b07882a/index/contentprovider.go).

### scip

[Repository at `fcb3cb3c679fe2da18141550f864b9e67afab297`](https://github.com/sourcegraph/scip/tree/fcb3cb3c679fe2da18141550f864b9e67afab297) · [License: Apache-2.0](https://github.com/sourcegraph/scip/blob/fcb3cb3c679fe2da18141550f864b9e67afab297/LICENSE)

Symbols, occurrences, roles, range encodings and symbol relationships. The protocol explicitly accommodates indexers at different precision levels. The format is not a correctness guarantee or a complete call graph.

Key source: [scip.proto](https://github.com/sourcegraph/scip/blob/fcb3cb3c679fe2da18141550f864b9e67afab297/scip.proto), [docs/scip.md](https://github.com/sourcegraph/scip/blob/fcb3cb3c679fe2da18141550f864b9e67afab297/docs/scip.md).

### scip-python

[Repository at `8b60bbce1f2a4c7a517776cb395bbafb2e731e4f`](https://github.com/sourcegraph/scip-python/tree/8b60bbce1f2a4c7a517776cb395bbafb2e731e4f) · [License: MIT](https://github.com/sourcegraph/scip-python/blob/8b60bbce1f2a4c7a517776cb395bbafb2e731e4f/LICENSE.txt)

Type-aware occurrence generation using the Pyright analyzer. Inspected by Swe2Max in the pinned checkout. Ambient dependency/toolchain discovery is separate from importing a previously generated index.

Key source: [packages/pyright-scip/src/treeVisitor.ts](https://github.com/sourcegraph/scip-python/blob/8b60bbce1f2a4c7a517776cb395bbafb2e731e4f/packages/pyright-scip/src/treeVisitor.ts), [packages/pyright-scip/src/virtualenv/PythonEnvironment.ts](https://github.com/sourcegraph/scip-python/blob/8b60bbce1f2a4c7a517776cb395bbafb2e731e4f/packages/pyright-scip/src/virtualenv/PythonEnvironment.ts).

### scip-typescript

[Repository at `e6d730c32189f14553d315b697f19bd8b60db65e`](https://github.com/sourcegraph/scip-typescript/tree/e6d730c32189f14553d315b697f19bd8b60db65e) · [License: Apache-2.0](https://github.com/sourcegraph/scip-typescript/blob/e6d730c32189f14553d315b697f19bd8b60db65e/LICENSE)

TypeScript-checker-backed symbol occurrences and project handling. Inspected by Swe2Max; parent checked entry-point/project setup. Full precision can depend on the project environment.

Key source: [src/ProjectIndexer.ts](https://github.com/sourcegraph/scip-typescript/blob/e6d730c32189f14553d315b697f19bd8b60db65e/src/ProjectIndexer.ts), [src/FileIndexer.ts](https://github.com/sourcegraph/scip-typescript/blob/e6d730c32189f14553d315b697f19bd8b60db65e/src/FileIndexer.ts), [src/main.ts](https://github.com/sourcegraph/scip-typescript/blob/e6d730c32189f14553d315b697f19bd8b60db65e/src/main.ts).

### repomix

[Repository at `55c6de6aebde4c38877fbcaf005c4cc396bf6e2d`](https://github.com/yamadashy/repomix/tree/55c6de6aebde4c38877fbcaf005c4cc396bf6e2d) · [License: MIT](https://github.com/yamadashy/repomix/blob/55c6de6aebde4c38877fbcaf005c4cc396bf6e2d/LICENSE)

Context packaging, tokenizer abstraction, syntax-guided compression and worker-based security checks. Parent re-fetched the listed source at the pinned commit. Compression and secret scanning retain limitations; exact tokenizer-library claims from the first draft were not carried forward.

Key source: [src/core/metrics/TokenCounter.ts](https://github.com/yamadashy/repomix/blob/55c6de6aebde4c38877fbcaf005c4cc396bf6e2d/src/core/metrics/TokenCounter.ts), [src/core/treeSitter/parseStrategies/PythonParseStrategy.ts](https://github.com/yamadashy/repomix/blob/55c6de6aebde4c38877fbcaf005c4cc396bf6e2d/src/core/treeSitter/parseStrategies/PythonParseStrategy.ts), [src/core/security/securityCheck.ts](https://github.com/yamadashy/repomix/blob/55c6de6aebde4c38877fbcaf005c4cc396bf6e2d/src/core/security/securityCheck.ts).

### ast-grep

[Repository at `14934d690a547abce8576baff9a1856a10ae7da8`](https://github.com/ast-grep/ast-grep/tree/14934d690a547abce8576baff9a1856a10ae7da8) · [License: MIT](https://github.com/ast-grep/ast-grep/blob/14934d690a547abce8576baff9a1856a10ae7da8/LICENSE)

Syntax-pattern matching, metavariables and root-kind filtering. Source inspected by Swe2Max. A structural match establishes syntax, not the identity or runtime behavior of the target.

Key source: [crates/core/src/matcher/pattern.rs](https://github.com/ast-grep/ast-grep/blob/14934d690a547abce8576baff9a1856a10ae7da8/crates/core/src/matcher/pattern.rs), [crates/core/src/meta_var.rs](https://github.com/ast-grep/ast-grep/blob/14934d690a547abce8576baff9a1856a10ae7da8/crates/core/src/meta_var.rs), [crates/core/src/match_tree/strictness.rs](https://github.com/ast-grep/ast-grep/blob/14934d690a547abce8576baff9a1856a10ae7da8/crates/core/src/match_tree/strictness.rs).

### dependency-cruiser

[Repository at `c580daf6477aa5619bacad9c9091c9b7cc81882d`](https://github.com/sverweij/dependency-cruiser/tree/c580daf6477aa5619bacad9c9091c9b7cc81882d) · [License: MIT](https://github.com/sverweij/dependency-cruiser/blob/c580daf6477aa5619bacad9c9091c9b7cc81882d/LICENSE)

Named allowed/forbidden/required dependency rules and explicit violations. Parent and Swe2Max source inspection. Adapt the rule concept to GraphPilot facts without running arbitrary repository-provided JavaScript configuration.

Key source: [src/validate/index.mjs](https://github.com/sverweij/dependency-cruiser/blob/c580daf6477aa5619bacad9c9091c9b7cc81882d/src/validate/index.mjs), [src/validate/match-dependency-rule.mjs](https://github.com/sverweij/dependency-cruiser/blob/c580daf6477aa5619bacad9c9091c9b7cc81882d/src/validate/match-dependency-rule.mjs), [src/validate/match-module-rule.mjs](https://github.com/sverweij/dependency-cruiser/blob/c580daf6477aa5619bacad9c9091c9b7cc81882d/src/validate/match-module-rule.mjs).

### code-graph

[Repository at `f5e72c074bf8b529d71472162e6d43cd6caaa5b6`](https://github.com/FalkorDB/code-graph/tree/f5e72c074bf8b529d71472162e6d43cd6caaa5b6) · [License: MIT](https://github.com/FalkorDB/code-graph/blob/f5e72c074bf8b529d71472162e6d43cd6caaa5b6/LICENSE)

Static Python resolver option, cached lexical/graph ranking, full-text metadata lookup and structural MCP operations. Parent and Swe2Max inspection. Default environment/LSP behavior and cross-project bare-name fallback need separate treatment from GraphPilot safe ingestion.

Key source: [api/analyzers/python/ts_resolver.py](https://github.com/FalkorDB/code-graph/blob/f5e72c074bf8b529d71472162e6d43cd6caaa5b6/api/analyzers/python/ts_resolver.py), [api/analyzers/python/analyzer.py](https://github.com/FalkorDB/code-graph/blob/f5e72c074bf8b529d71472162e6d43cd6caaa5b6/api/analyzers/python/analyzer.py), [api/mcp/tools/structural.py](https://github.com/FalkorDB/code-graph/blob/f5e72c074bf8b529d71472162e6d43cd6caaa5b6/api/mcp/tools/structural.py), [api/graph.py](https://github.com/FalkorDB/code-graph/blob/f5e72c074bf8b529d71472162e6d43cd6caaa5b6/api/graph.py).

### GitNexus

[Repository at `b961e695cabae1e0c2a0c1641fd0f6e2ffd15e19`](https://github.com/abhigyanpatwari/GitNexus/tree/b961e695cabae1e0c2a0c1641fd0f6e2ffd15e19) · [License: PolyForm Noncommercial 1.0.0](https://github.com/abhigyanpatwari/GitNexus/blob/b961e695cabae1e0c2a0c1641fd0f6e2ffd15e19/LICENSE)

Resolution-pass decomposition; resolved, suppressed and fallback-guessed outcomes; process/community views and change-oriented tools. Parent and Swe2Max source inspection. Numeric evidence weights are heuristics. This license is not an unrestricted commercial reuse grant; treat it as a source-available comparator.

Key source: [gitnexus/src/core/ingestion/scope-resolution/resolution-outcome.ts](https://github.com/abhigyanpatwari/GitNexus/blob/b961e695cabae1e0c2a0c1641fd0f6e2ffd15e19/gitnexus/src/core/ingestion/scope-resolution/resolution-outcome.ts), [gitnexus/src/core/ingestion/process-processor.ts](https://github.com/abhigyanpatwari/GitNexus/blob/b961e695cabae1e0c2a0c1641fd0f6e2ffd15e19/gitnexus/src/core/ingestion/process-processor.ts), [gitnexus/src/core/ingestion/community-processor.ts](https://github.com/abhigyanpatwari/GitNexus/blob/b961e695cabae1e0c2a0c1641fd0f6e2ffd15e19/gitnexus/src/core/ingestion/community-processor.ts), [gitnexus-shared/src/scope-resolution/evidence-weights.ts](https://github.com/abhigyanpatwari/GitNexus/blob/b961e695cabae1e0c2a0c1641fd0f6e2ffd15e19/gitnexus-shared/src/scope-resolution/evidence-weights.ts), [gitnexus/bench/impact-pdg/README.md](https://github.com/abhigyanpatwari/GitNexus/blob/b961e695cabae1e0c2a0c1641fd0f6e2ffd15e19/gitnexus/bench/impact-pdg/README.md).

### CodeGraphContext

[Repository at `1b595a61663d60862ac20aca2422ea187671c01c`](https://github.com/CodeGraphContext/CodeGraphContext/tree/1b595a61663d60862ac20aca2422ea187671c01c) · [License: MIT](https://github.com/CodeGraphContext/CodeGraphContext/blob/1b595a61663d60862ac20aca2422ea187671c01c/LICENSE)

Multi-language pipeline, parse-failure accounting, per-call resolution diagnostics and debounced watching. Parent source inspection via commit-pinned raw files. Its confidence tiers and fallback policies require evaluation rather than direct promotion to verified facts.

Key source: [src/codegraphcontext/tools/indexing/pipeline.py](https://github.com/CodeGraphContext/CodeGraphContext/blob/1b595a61663d60862ac20aca2422ea187671c01c/src/codegraphcontext/tools/indexing/pipeline.py), [src/codegraphcontext/tools/indexing/scip_pipeline.py](https://github.com/CodeGraphContext/CodeGraphContext/blob/1b595a61663d60862ac20aca2422ea187671c01c/src/codegraphcontext/tools/indexing/scip_pipeline.py), [src/codegraphcontext/tools/indexing/resolution/calls.py](https://github.com/CodeGraphContext/CodeGraphContext/blob/1b595a61663d60862ac20aca2422ea187671c01c/src/codegraphcontext/tools/indexing/resolution/calls.py), [src/codegraphcontext/core/watcher.py](https://github.com/CodeGraphContext/CodeGraphContext/blob/1b595a61663d60862ac20aca2422ea187671c01c/src/codegraphcontext/core/watcher.py).

### codebase-memory-mcp

[Repository at `354ccecbe612a9fdb624396a6738fa87f2617434`](https://github.com/DeusData/codebase-memory-mcp/tree/354ccecbe612a9fdb624396a6738fa87f2617434) · [License: MIT](https://github.com/DeusData/codebase-memory-mcp/blob/354ccecbe612a9fdb624396a6738fa87f2617434/LICENSE)

Separate extraction/enrichment passes, static test relations, explicit resource-limit failure states, staged artifacts and evaluation guidance. Parent source/docs inspection. Test naming and key/symbol matches are heuristics; published token/speed outcomes were not reproduced.

Key source: [src/pipeline/pipeline.c](https://github.com/DeusData/codebase-memory-mcp/blob/354ccecbe612a9fdb624396a6738fa87f2617434/src/pipeline/pipeline.c), [src/pipeline/pass_tests.c](https://github.com/DeusData/codebase-memory-mcp/blob/354ccecbe612a9fdb624396a6738fa87f2617434/src/pipeline/pass_tests.c), [src/pipeline/pass_configlink.c](https://github.com/DeusData/codebase-memory-mcp/blob/354ccecbe612a9fdb624396a6738fa87f2617434/src/pipeline/pass_configlink.c), [src/pipeline/artifact.c](https://github.com/DeusData/codebase-memory-mcp/blob/354ccecbe612a9fdb624396a6738fa87f2617434/src/pipeline/artifact.c), [docs/INDEX_RESOURCE_LIMITS.md](https://github.com/DeusData/codebase-memory-mcp/blob/354ccecbe612a9fdb624396a6738fa87f2617434/docs/INDEX_RESOURCE_LIMITS.md), [docs/MEASURING_SAVINGS.md](https://github.com/DeusData/codebase-memory-mcp/blob/354ccecbe612a9fdb624396a6738fa87f2617434/docs/MEASURING_SAVINGS.md).

### serena

[Repository at `d9e4c796fae0207ba6848d1df4b331122a5567b5`](https://github.com/oraios/serena/tree/d9e4c796fae0207ba6848d1df4b331122a5567b5) · [License: GPL-3.0-or-later application; MIT SolidLSP](https://github.com/oraios/serena/blob/d9e4c796fae0207ba6848d1df4b331122a5567b5/LICENSE)

Symbol-addressed navigation/reference tools over language servers. Swe2Max source inspection; parent read component licensing. Direct reuse requires checking the relevant component and obligations; a live LSP workspace is a different product mode from immutable archived-source analysis.

Key source: [src/serena/tools/symbol_tools.py](https://github.com/oraios/serena/blob/d9e4c796fae0207ba6848d1df4b331122a5567b5/src/serena/tools/symbol_tools.py), [src/solidlsp](https://github.com/oraios/serena/tree/d9e4c796fae0207ba6848d1df4b331122a5567b5/src/solidlsp), [LICENSES](https://github.com/oraios/serena/tree/d9e4c796fae0207ba6848d1df4b331122a5567b5/LICENSES).

### LightRAG

[Repository at `aaebfe1bb8d55deb6a4304d357a3bf4c92fcd40a`](https://github.com/HKUDS/LightRAG/tree/aaebfe1bb8d55deb6a4304d357a3bf4c92fcd40a) · [License: MIT](https://github.com/HKUDS/LightRAG/blob/aaebfe1bb8d55deb6a4304d357a3bf4c92fcd40a/LICENSE)

Entity/relationship-oriented retrieval and context merging, inspected by Swe2Max. The relevant pattern is diversification. Model-authored graph facts and mandatory extraction-time model calls are not proposed for GraphPilot core indexing.

Key source: [lightrag/operate.py](https://github.com/HKUDS/LightRAG/blob/aaebfe1bb8d55deb6a4304d357a3bf4c92fcd40a/lightrag/operate.py).

### deepwiki-open

[Repository at `d92819a9c9f3b99416e3580ff235fc9d3adf8b89`](https://github.com/AsyncFuncAI/deepwiki-open/tree/d92819a9c9f3b99416e3580ff235fc9d3adf8b89) · [License: MIT](https://github.com/AsyncFuncAI/deepwiki-open/blob/d92819a9c9f3b99416e3580ff235fc9d3adf8b89/LICENSE)

Wiki organization, source-link presentation and task progress. Parent inspected commit-pinned sources. The wiki task registry is explicitly in-memory; source URLs in the inspected helper use a branch context, so retain GraphPilot durable jobs and commit-pinned evidence.

Key source: [api/services/wiki/structure.py](https://github.com/AsyncFuncAI/deepwiki-open/blob/d92819a9c9f3b99416e3580ff235fc9d3adf8b89/api/services/wiki/structure.py), [api/services/wiki/content.py](https://github.com/AsyncFuncAI/deepwiki-open/blob/d92819a9c9f3b99416e3580ff235fc9d3adf8b89/api/services/wiki/content.py), [api/services/wiki/tasks.py](https://github.com/AsyncFuncAI/deepwiki-open/blob/d92819a9c9f3b99416e3580ff235fc9d3adf8b89/api/services/wiki/tasks.py), [api/rag/rag.py](https://github.com/AsyncFuncAI/deepwiki-open/blob/d92819a9c9f3b99416e3580ff235fc9d3adf8b89/api/rag/rag.py).

### sourcebot

[Repository at `a5fcd2703e605c08d49ebda9b965997eaf00c21b`](https://github.com/sourcebot-dev/sourcebot/tree/a5fcd2703e605c08d49ebda9b965997eaf00c21b) · [License: MIT for inspected public repository contents](https://github.com/sourcebot-dev/sourcebot/blob/a5fcd2703e605c08d49ebda9b965997eaf00c21b/LICENSE.md)

Public configuration/deployment/schema repository, with 68 tree entries at inspection and no application runtime source in that tree. Parent API-tree/raw inspection and Swe2Max verification. Product workflow claims come from official docs; the runtime license is not inferred from this MIT file.

Key source: [README.md](https://github.com/sourcebot-dev/sourcebot/blob/a5fcd2703e605c08d49ebda9b965997eaf00c21b/README.md), [docker-compose.yml](https://github.com/sourcebot-dev/sourcebot/blob/a5fcd2703e605c08d49ebda9b965997eaf00c21b/docker-compose.yml), [schemas](https://github.com/sourcebot-dev/sourcebot/tree/a5fcd2703e605c08d49ebda9b965997eaf00c21b/schemas), [tools](https://github.com/sourcebot-dev/sourcebot/tree/a5fcd2703e605c08d49ebda9b965997eaf00c21b/tools).

## Documentation-only additional comparison

[Microsoft GraphRAG indexing](https://microsoft.github.io/graphrag/index/overview/), [global search](https://microsoft.github.io/graphrag/query/global_search/), and [local search](https://microsoft.github.io/graphrag/query/local_search/) were reviewed at documentation level. Its standard pipeline documents model-based entity/relationship extraction, community detection/reports and embeddings. Graph-only grouping can be evaluated separately from generated summaries. No GraphRAG source-level or runtime-comparison claim is made.

## Primary product sources

Official documentation establishes a documented capability, not independently verified quality or performance. The first drafts mixed current and older material for some products; the links below are the sources retained for the final comparison.

**Sourcegraph:** [Search syntax](https://sourcegraph.com/docs/code-search/queries), [Navigation](https://sourcegraph.com/docs/code-navigation), [Precise navigation](https://sourcegraph.com/docs/code-navigation/precise-code-navigation), [Deep Search, including sources and sharing caveats](https://sourcegraph.com/docs/deep-search), [MCP](https://sourcegraph.com/docs/api/mcp).

**Sourcebot:** [Overview](https://docs.sourcebot.dev/docs/overview), [Ask](https://docs.sourcebot.dev/docs/features/ask/ask-sourcebot), [MCP](https://docs.sourcebot.dev/docs/features/mcp-server), [Navigation](https://docs.sourcebot.dev/docs/features/code-navigation), [Permission syncing](https://docs.sourcebot.dev/docs/features/permission-syncing), [Sharing](https://docs.sourcebot.dev/docs/features/ask/chat-sharing), [Branch indexing](https://docs.sourcebot.dev/docs/features/search/multi-branch-indexing), [Architecture](https://docs.sourcebot.dev/docs/misc/architecture), [v5 to v6 guide](https://docs.sourcebot.dev/docs/upgrade/v5-to-v6-guide).

**GitHub:** [Code search limits](https://docs.github.com/en/search-github/github-code-search/about-github-code-search), [Code search syntax](https://docs.github.com/en/search-github/github-code-search/understanding-github-code-search-syntax), [Code navigation](https://docs.github.com/en/repositories/working-with-files/using-files/navigating-code-on-github), [Copilot Spaces](https://docs.github.com/en/copilot/concepts/context/spaces).

**Augment:** [Context Engine MCP and local/remote indexing](https://docs.augmentcode.com/context-services/mcp/overview), [Context services](https://docs.augmentcode.com/context-services/overview), [Context connector pipeline](https://docs.augmentcode.com/context-services/context-connectors/how-it-works).

**Cursor:** [Current Search page](https://cursor.com/docs/agent/tools/search), [Security](https://cursor.com/security).

**CodeScene:** [Change coupling](https://codescene.io/docs/guides/technical/change-coupling.html), [Code health](https://codescene.io/docs/guides/technical/code-health.html), [Hotspots](https://codescene.io/docs/guides/technical/hotspots.html).

**Swimm:** [Auto-sync explanation](https://swimm.io/blog/how-does-swimm-s-auto-sync-feature-work), [CI documentation checks](https://swimm.io/blog/continuous-documentation-through-continuous-integration-with-swimm), [Documentation overview](https://docs.swimm.io/).

**Greptile:** [Canonical introduction](https://www.greptile.com/docs/introduction), [Graph context](https://www.greptile.com/docs/how-greptile-works/graph-based-codebase-context), [Memory and learning](https://www.greptile.com/docs/how-greptile-works/memory-and-learning).

**SciTools Understand:** [Local MCP server](https://docs.scitools.com/help/ai/connect-via-mcp.html), [Documentation](https://docs.scitools.com/).

**Devin DeepWiki:** [Repository wikis and configurable structure](https://docs.devin.ai/work-with-devin/deepwiki).

**Storage/search references:** [PostgreSQL pg_trgm](https://www.postgresql.org/docs/current/pgtrgm.html), [PostgreSQL full-text search](https://www.postgresql.org/docs/current/textsearch.html), [FalkorDB indexes](https://docs.falkordb.com/cypher/indexing), [FalkorDB full-text index](https://docs.falkordb.com/cypher/indexing/fulltext-index).

## Local evidence and reproducibility

See [EVIDENCE.json](EVIDENCE.json) for timing/model provenance and the artifact inventory; [graph-probes.json](graph-probes.json), [local-probes.json](local-probes.json), [self-analysis.json](self-analysis.json), [search-index-probe.json](search-index-probe.json), [fulltext-check.json](fulltext-check.json), [adversarial-probes.json](adversarial-probes.json) and [correctness-probes.json](correctness-probes.json) for observations. Research-only scripts are retained under [probes/](probes/README.md). They use isolated temporary stores and never load the project test fixture that truncates `graphpilot_test`. Source self-analysis includes hashes of the observed dirty working-tree files, because Git HEAD alone does not identify that source state.

[REPOSITORIES.json](REPOSITORIES.json) records the 17 pinned entries; [SOURCE_PATH_CHECKS.json](SOURCE_PATH_CHECKS.json) records 72 source/license path checks, including public-tree directory checks. [REVIEW_DECISIONS.md](REVIEW_DECISIONS.md) summarizes corrections accepted after model/parent review. [IMPLEMENTATION_HANDOFF.md](IMPLEMENTATION_HANDOFF.md) supplies the separate implementation chat's concrete release plan.

[CHECKOUT_PIN_CHECKS.json](CHECKOUT_PIN_CHECKS.json) confirms all 11 retained shallow checkouts match their recorded SHAs. Other inspected entries use pinned raw/API-tree evidence. [DESIGN_NOTES.md](DESIGN_NOTES.md) records accepted design details and corrections from the final review, with independent [edge-case checks](design-edge-checks.json) and an [abstract traversal contract check](traversal-contract-check.json).

## Limits on adoption

GitNexus is recorded as source-available under a noncommercial license. Serena licensing is component-specific. Sourcebot's public repository license does not establish the runtime image's license. Other listed permissive licenses also require attention to notices and third-party code if any source is later reused. This report recommends studying designs and implementing narrowly evaluated GraphPilot capabilities; it does not authorize indiscriminate copying.
