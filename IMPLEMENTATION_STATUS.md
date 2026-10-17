# GraphPilot implementation and verification status

The complete, unchanged specification is preserved in `docs/REQUIREMENTS.md`.
The native demonstration is verified. Full container/production verification is
**open with missing host runtime prerequisites and residual image findings**: no Docker daemon or rootless UID
mapping helpers, with interactive sudo required to install those helpers. Evidence
lives in tests and reports; native checks are not counted as container checks.

October 17 local follow-up: **110 tests passed in 15.58 s**, including 29 release-gate
cases. CI now enforces complete Python/npm lock audits and a container-image gate
that rejects missing evidence. Fresh Python (52 packages) and both npm audits report
zero known vulnerabilities. Ruff/Actionlint/Compose configuration checks pass.
Actual image scans/builds remain outstanding; existing image findings are unchanged.
See `docs/RELEASE_GATE_VERIFICATION.json`.

| Gate | Current implementation and authoritative evidence | Outstanding before the full gate passes |
|---|---|---|
| 0 — investigation | Verified: empty initial directory, host resources/tools, actual CodeGraph checkout inspected, architecture documented. No pre-existing app/tests. | None for the empty-project baseline. |
| 1 — infrastructure | Native PostgreSQL 18.6, real FalkorDBLite, API, external durable worker and Vite run. Migrations/readiness/HTTP + E2E pass. Compose, Dockerfiles, persistent volumes, private DB network defined. | Native DB persistence, API reconnection and worker recovery after a 3-second DB outage passed. Container build/start/restart still unverified; Docker daemon absent. |
| 2 — authentication | 110-test suite includes Argon2id, signup/login/logout, expiry, disabled accounts, sessions, CSRF/origins, membership/RBAC, audit, one-time reset and revocation. Browser user/admin login journeys pass. | Authenticated local SMTP/STARTTLS and real local Nginx/TLS gateway checks pass. External inbox delivery and a public HTTPS deployment remain unverified. |
| 3 — frontend | All named route families implemented with real API data, responsive light/dark UI. User E2E covers connect/index/graph/evidence/context/impact/settings/logout; admin E2E covers bootstrap/roles/enforcement/audit. Build passes; screenshots captured. | Independent reviewer scored all six fixes resolved; DESIGN.md, design sidecar and surface brief verified; Tablet empty/error/retry checks have been added to the browser regression. Recent questions and CI failures now use authorized published snapshots and pass desktop/mobile browser checks. |
| 4 — ingestion | Actual public GitHub clone, allowed local committed Git and validated ZIP adapters. Python AST never executes code. Resource/path/protocol limits. Live itsdangerous HTTP ingestion passed. | Streamed HTTP/multipart, AST/declaration/call and global graph bounds now pass regression tests. A 400-file/4000-function index now passes with actual worker CPU/RSS sampling. Nested ignores now match Git check-ignore fixture results, obey explicit budgets and prune excluded source artifacts. |
| 5 — schema | Typed graph nodes/edges, UUID+branch namespaces, stable IDs, repeated declaration handling, parameterized bounded reads, source artifacts outside graph. Real DB isolation/integrity tests. | Branch-local selection, immutable snapshot/source navigation and branch-scoped GitHub publication now pass API/browser checks. Snapshot retirement/removal now pass API, fault recovery and real worker/browser checks. Conceptual decision/fix types appear only when reliable evidence exists. |
| 6 — history/CI | GitHub REST commits, issues, PRs/commits/files, workflow failures; cursor resume, stable dedup, rate-limit deferral, bounded retries. Recorded fixtures pass. | Selected failed-job logs now download/archive/redact with enforced expiry, scope and integrity checks; recorded-fixture browser download passes. PR and commit file-detail pages now resume atomically. Immutable commit details are reused; exact pytest node IDs link only at matching commits. Remaining: external successful log access; GitHub PR limits (250 commits/3000 files) are disclosed. |
| 7 — retrieval | Symbol, neighbor, path, impact, history and context operations. Exact/lexical scoring and direct graph evidence; actual source regions; scoped queries. Fixed fixture chain and real-repo want_bytes verified. 20-session HTTP baseline measured. | Nine fixed evidence tasks pass with actual query accounting, latency and context sizes in RETRIEVAL_BENCHMARK.json. Revision selection and tenant isolation pass. Broader ranking evaluation remains a quality improvement. |
| 8 — AI | Optional OpenAI-compatible provider with evidence/relationship boundary, time/context/citation limits, no shell/tools. Honest graph-only and provider-failure fallback tested. | User selected graph-only operation with no model available. No real-provider synthesis is claimed. Provider success and model-behavior prompt-injection evaluation remain unexecuted optional integration checks; deterministic known tasks pass. |
| 9 — incremental | Real local Git test changes one file, skips another, removes stale calls, retains old graph and proves second unchanged scan has zero graph writes. Graph copies receive semantic diffs. | Real file rename/deletion, interrupted publication, lost commit acknowledgement and killed-worker recovery pass; bounded retirement now preserves heads/conversation pins and shared source trees, with durable retry after cleanup failure. |
| 10 — admin/monitoring | User/role/disable management, explicit read/write memberships, jobs/retry/cancel, readiness, audit and actual count API. Backend + admin browser enforcement verified. | Ownership transfer, worker heartbeats and measured storage/request/graph-read/error observations are implemented with API/browser checks. Single-instance administration passes; wider retry/cancel browser permutations and multi-instance aggregation are additional quality work. Durable allowlisted CI log settings now pass API and isolated browser checks. |
| 11 — comprehensive tests | Ruff, TypeScript/build, 110 backend/release tests, 3 real-browser journeys, real HTTP clone/search/logout, dependency audits, 20-session/200-query benchmark. CI config added. | Remote execution of the defined CI jobs; current full scope is mapped in docs/REQUIREMENTS_AUDIT.md. |
| 12 — production | Config validation, optimized image definitions, private DB network, migrations, gateway CSP, headers, HTTPS/secret/backup guidance in README. | Runtime image/production checks, container backup/restore verification, container-image audit. The requirement audit is recorded in docs/REQUIREMENTS_AUDIT.md. Native retention and durable owner removal are implemented and tested. |

## Latest executed checks

- `uv run ruff check api tests scripts migrations` — passed.
- `uv run pytest -q` — 110 passed in 15.58 s; one upstream TestClient/httpx deprecation warning.
- `npm --prefix app run build` — passed (initial JS ~386 kB, graph ~447 kB).
- `PLAYWRIGHT_CHANNEL=chrome npx playwright test` — three journeys passed in 49.6 s after restarting the updated API/worker; includes isolated archives, mobile/tablet layouts and access enforcement.
- `uv run python -m scripts.verify-live` — passed, real public repository, 50 files,
  196 nodes / 319 edges, exact `want_bytes` source, graph-only context, logout denial.
- `uv run python -m scripts.benchmark` — 20 authenticated sessions, 200/200 correct
  HTTP searches, p50 87.96 ms / p95 143.41 ms on a 4-file fixture. Baseline, not SLA.
- npm production/root audits — zero reported vulnerabilities.
- Python production dependency audit — no known vulnerabilities; JSON report retained.
- Impeccable mechanical detector — no findings; independent visual review requested
  six material fixes, implemented together; reviewer scored all six resolved (ship at fix-list scope).

## Remaining environment verification

1. Supply a Docker runtime, then execute image build, Compose startup/restart,
   container-volume backup/restore and image audit. Rootless prerequisites are
   missing and installing them requires interactive sudo authentication.
2. Run remote GitHub Actions after a project remote is configured; the user confirmed no destination is available yet. Actionlint and Git candidate scanning pass locally.
3. Verify external SMTP inbox delivery and authenticated GitHub logs when those
   services are configured. Local authenticated SMTP/TLS is verified. The user selected graph-only mode for this demo. A public HTTPS deployment still needs a target and certificate.

The original specification is mapped in `docs/REQUIREMENTS_AUDIT.md`. Native
persistence/restore and resource/crash/security observations are executed evidence;
container checks remain unexecuted, with no fabricated success.

Detailed results, failed attempts and limits: `docs/TEST_REPORT.md`.
No credentials or successful external-provider results have been fabricated.

## Infrastructure observations

`docker compose config --quiet` passed using the official standalone Compose
2.39.4 binary and non-secret validation inputs. This validates configuration, not
container execution. `docs/PERSISTENCE_VERIFICATION.json` records actual native
PostgreSQL restart, owned FalkorDB shutdown/restart, surviving relational/graph
probes and API reconnection. Generated E2E accounts/repositories were cleaned up;
audit history remains. The normal application starts with real, user-owned data.

## Branches, snapshots and CI log phase (October 16)

- Migrations 0003/0004 add branch heads, immutable graph/source snapshot metadata,
  job branch capture, conversation snapshot references and expiring log archives.
- Real two-branch Git fixtures prove default-head stability, cross-branch node
  rejection, historical source after symbol replacement, snapshot ownership,
  read-only access and graph publication after interrupted GitHub sync.
- Public itsdangerous main/stable browser checks pass with different real SHAs,
  selection persistence, immutable citation links, read-only snapshots and mobile layout.
- CI fixture tests prove token-free redirect downloads, byte/host/rate limits,
  redaction before storage, archive deduplication, scoped downloads, integrity/expiry
  enforcement, idempotent purge and omission of saved complete log excerpts.
- An external unauthenticated failed-job log request returned HTTP 403 (run
  38830705597, job 116748581860); no successful external archive was fabricated.
- Recorded fixture browser tests run isolated from development data and show real
  redacted evidence/downloads. Successful provider authentication remains unverified.

Concurrent real graph snapshot test: two independent namespaces, six GRAPH.COPY/diff publications each, passed after bounded retry of the documented transient fork rejection. Unknown write failures remain fatal. Current full browser run includes three passing journeys; the isolated log fixture is removed after the test.

Native restore drill passed (`docs/RESTORE_VERIFICATION.json`): API/worker writers
stopped, private PostgreSQL/RDB/artifact backups hashed, isolated relational and
graph instances restored, actual HTTP login/graph/source evidence verified,
original API and worker restarted. The isolated restore database/server/artifacts
and probe account/repository were removed; a private ignored backup remains. This
does not prove container-image or Docker-volume restore.


## Capacity, history and lifecycle phase (October 16)

Current suite: **64 passed**, real PostgreSQL/FalkorDB; current full browser run:
**3 passed, 48.4 s**. Current live clone verification: **5.18 s**. Exact measured
retrieval cases live in `docs/RETRIEVAL_BENCHMARK.json`; current 20-session load
results are in `docs/PERFORMANCE.json`. Failed development-cache/browser attempts
and their fixes are recorded in `docs/TEST_REPORT.md`.

HTTP spooling, parser/graph budgets, commit evidence preservation, resumable PR and
commit detail pages, nine retrieval tasks, exact matching-commit pytest log links,
recent workspace data, durable retirement and owner removal now have implemented
and executed checks. Migration 0007 is applied to the native development database.
The user explicitly chose graph-only operation; a real model remains unconfigured.

Retirement keeps heads, conversation pins and shared source artifacts. Cleanup is
bounded and can defer; it does not impose a hard disk quota. Removal deletes only
owned graph/artifact/input namespaces and preserves authoritative local Git. Native
backup/restore is verified; Compose now fixes artifact storage at its volume path,
but actual container build/runtime/restore still needs an available Docker daemon.


Final local audit additions: 64 backend tests pass (13.20 s). Real metadata sync
published 177 entities in 25 GitHub requests and removed its own probe repository.
A killed real worker recovers through an expired durable lease; a stale worker is
fenced. Production HTTPS profile checks pass. The 400-file/4000-function fixture
indexed in 1.08 s with 0.57 s worker CPU and 106.03 MiB sampled worker RSS peak;
these exclude graph-process CPU and are not maximum capacity guarantees. Current
schema backup/restore was rerun successfully. The lost-acknowledgement publication
guard and actual Git rename/delete/interruption retry have regression coverage.


## New-chat continuation verification (October 16)

The remaining independent checks were implemented and executed: 81 real-database
backend tests, all three browser journeys (49.6 s), production frontend build,
real authenticated SMTP/STARTTLS transactions and a real native Nginx/TLS gateway.
The SMTP client now verifies certificates and hostnames. Five protocol failures
preserve the prior reset token and session and return safe errors. Production
validates its public URL and disables Swagger, ReDoc and the schema.

Gateway checks include the built JavaScript MIME type, local certificate trust,
Secure cookies withheld over plaintext, CSP/CORS/CSRF, API/gateway body limits,
worker indexing, exact source, outsider denial, restart recovery and owned removal.
Disposable gateway data and browser records were cleaned up. Graph-only mode is
unchanged. Evidence: `GATEWAY_VERIFICATION.json` and `SMTP_VERIFICATION.json`.

Deployment review fixes cover recursive build-context exclusions, ignored backups,
service DNS refresh, forwarded-header replacement and explicit CI readiness checks.
The SWE-2 Max review's PostgreSQL volume finding was rejected after checking the
actual 18.6 image: its declared volume is `/var/lib/postgresql`, matching Compose.
Image manifests exist, but registry metadata is not execution or vulnerability
evidence (`IMAGE_METADATA_VERIFICATION.json`).

A guarded disposable Compose build/start/recreation/backup/restore harness and CI
container/image-audit job are written. Only the harness's configuration path has
executed (`CONTAINER_VERIFICATION.json`); no Docker runtime is present. Actionlint
passes. Candidate-only Gitleaks scanning passes with exact exceptions for invalid
redaction fixtures; ignored credentials, backups and build outputs stay excluded.
No commit, remote publication, external mail/log access or public TLS success is
claimed. See `CONTINUATION_VERIFICATION.md` for current scope and commands.

## Image follow-through — October 17 (local time)

All four selected upstream filesystem scans eventually completed, including
FalkorDB. The replacement Nginx base has no high/critical findings; Python Trixie
still has 44 high findings and FalkorDB has 36 high findings. The PostgreSQL Trixie
alternative has 85 high/two critical findings. None were suppressed. The current
PostgreSQL definition instead uses the official 18.6 Alpine candidate and removes
its unused Go-based helper while running as `postgres`. Its publisher inventory,
with an explicitly sourced Alpine distribution declaration, reports 24 high/one
critical finding, all in the bundled Go stdlib; the derived image must be built
and audited to verify their removal. Actual container initialization, permissions,
restart/restore and final image auditing remain open.

The initial inventory analyses lacked OS identification and are marked limited.
The complete filesystem scans are separate from those inventory results. An
isolated 40-package production-only native environment imports the production API
successfully without development dependencies. See `IMAGE_SECURITY_REVIEW.md`,
`REMOTE_IMAGE_AUDIT*.json`, `POSTGRES_ALPINE_INVENTORY.json` and
`PRODUCTION_IMPORT_VERIFICATION.json`. Native services and graph-only mode remain
unchanged; no production certification is implied.
