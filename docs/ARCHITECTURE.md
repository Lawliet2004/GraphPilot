# GraphPilot architecture

## Inspection (2026-10-16)
The working directory was empty and was not a Git repository. No application,
configuration, credentials, tests, or database services existed to preserve.
Host: Ubuntu 26.04, 12 CPUs, 14 GiB RAM (~3 GiB available), Python 3.14,
Node 22, npm and uv; Docker, PostgreSQL and Redis/FalkorDB were absent.
Python 3.12 is installed using uv for the application.

Inspected a real shallow checkout of https://github.com/FalkorDB/code-graph at
`2a7a52c0abb529c93e9f571e7358e097f1b76ab3` outside this project in
`/tmp/graphpilot-upstream-codegraph`. Read package manifests, API authentication,
graph backend selection, source orchestration, Python analyzer/static resolver,
and structural retrieval implementation. Its source registers Python, Java,
C#, JavaScript and Kotlin; this is source evidence, not a claim that all parsers
are correct. Upstream tests were not run: no upstream runtime is adopted, and
this empty project has no pre-existing test baseline.

## Decisions
- React + Vite + TypeScript, TanStack Query, Router, Lucide and Cytoscape.
- FastAPI with one session-cookie authentication model. PostgreSQL/SQLAlchemy
  stores users, hashed sessions, repository membership, jobs, query history,
  source manifests, synchronization cursors and audit events. Alembic migrations.
- A separate durable worker claims PostgreSQL jobs with row locks, leases and
  recovery. Repository jobs serialize with an advisory lock. No in-process-only
  background indexing.
- Real FalkorDB for graph storage. An embedded FalkorDBLite is a development/test
  option when Docker is absent; it is the same graph engine, not mocked storage.
- Repository UUID + branch digest + snapshot generation determine graph names.
  A verified graph generation becomes visible only after successful ingestion.
  Membership is checked before every graph/evidence/AI operation.
- Stable semantic entity IDs, typed relationships, bounded parameterized queries.
  Historical graph snapshots remain distinct. Code bodies live in protected
  filesystem artifacts, not graph properties.
- Python stdlib AST provides safe static indexing without executing source code,
  importing dependencies, or launching a repository-provided interpreter. Known
  unresolved dynamic calls are reported. Other languages initially get file
  nodes only; they are not advertised as semantically indexed.
- Exact and lexical retrieval, bounded traversals and transparent ranking work
  without an LLM. An optional OpenAI-compatible model receives quoted evidence
  with opaque citation IDs; it gets no database credentials or shell tools.

## Upstream reuse and limits
Reuse CodeGraph's broad module boundaries, File/Function/Class + DEFINES/CALLS/
IMPORTS semantics and bounded neighbor/path/impact retrieval approach. No code
is copied or vendored at present. The upstream web/auth layer is unsuitable for
multi-user isolation without major changes. Its Python resolver explicitly uses
a cross-project bare-name fallback; GraphPilot does not mark ambiguous matches
as verified. Its analyzer may select a repository's virtualenv and language
server; GraphPilot must not execute repository code. Reusing that full pipeline
would violate this deployment's safety/resource constraints. The smaller AST
adapter is an explicit, tested choice, not assumed language parity.

## Deployment
Compose runs frontend gateway, API, worker, PostgreSQL and FalkorDB with private
database networks and durable volumes. Native tools enable testing on this host.
All application data access passes through FastAPI. External GitHub and model
content is untrusted. No generic Cypher, command execution, or code mutation API.
