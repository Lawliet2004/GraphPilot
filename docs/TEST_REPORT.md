# GraphPilot verification report — ongoing

## Latest release verification — October 17

All six remote CI jobs pass: **111 backend/release tests in 22.79 s** and
**three browser journeys in 39.1 s**, plus builds, full dependency/secret audits,
actual Docker startup/private networking/non-root databases/indexing/recreation/
volume backup+restore and strict image audits. Four actual runtime images report
**zero known vulnerabilities across reported severities** with no suppressions.
The complete local Compose drill also passes and removes its owned deployment.
Ruff and Actionlint pass. Docker Engine/Compose/Buildx are installed; the repository
is published on `main` under Lawliet2004 with no co-authors.

Real authenticated GitHub job-log download now passes through the production
adapter (token in memory only; no persisted artifact from that probe). The
containerized safe Git adapter fetch and independent graph-container restore pass.
Native HTTPS/local SMTP evidence remains separate from public hosting/external
inbox delivery, which are deferred/unconfigured.

Current evidence: `CI_VERIFICATION.json`, `CONTAINER_VERIFICATION.json`,
`CONTAINER_LOCAL_VERIFICATION.json`, `CONTAINER_IMAGE_AUDIT.json`,
`GITHUB_LOG_VERIFICATION.json`, `CONTAINER_GIT_VERIFICATION.json` and
`GRAPH_CONTAINER_PERSISTENCE.json`. Earlier counts/status claims below describe
historical observations and are superseded for release readiness by these reports.

Devin's exact swe-2-max documentation review completed. Its separate container
review timed out after 240 seconds without a final result; it is not a passing check.

## Earlier local continuation verification

October 17 local release-check follow-up supersedes the previous 81-test total:
**110 passed in 15.58 s**, including 29 image-gate regression cases. Ruff and
Actionlint pass. Fresh hashed Python-lock audit (52 packages, none skipped) and
both complete npm-lock audits report zero known vulnerabilities. Compose config
validation covers all six services; the actual audit CLI rejects that
configuration-only report with exit 1 before invoking a scanner. Existing real
upstream JSON reports were also checked for parser compatibility, without claiming
a new scan. No Docker/remote CI execution occurred. Evidence:
`RELEASE_GATE_VERIFICATION.json`.

- Full backend regression: **81 passed in 15.75 s** on real PostgreSQL/FalkorDB;
  one upstream TestClient deprecation warning. Targeted SMTP/auth: **12 passed**.
- Browser regression after updated API/worker restart: **3 passed in 49.6 s**.
  Generated main-environment accounts/repositories were removed afterward.
- Ruff, TypeScript/production build and Actionlint 1.7.12 pass. The complete
  exported Python lock (52 audited packages, including development SMTP testing)
  reports no known vulnerabilities in `CONTINUATION_DEPENDENCY_AUDIT.json`.
- Actual authenticated loopback SMTP/STARTTLS passes; missing TLS, untrusted/wrong
  certificates, rejected authentication and rejected delivery fail safely without
  replacing prior reset tokens. External inbox delivery is still unverified.
- Actual native Nginx/HTTPS gateway checks pass against the production API/worker,
  built frontend and disposable real data. Cookies, certificate trust, CSP/CORS/
  CSRF, body limits, source isolation and restart recovery are recorded in
  `GATEWAY_VERIFICATION.json`. This is neither container nor public TLS evidence.
- Candidate-only Gitleaks passes with exact invalid-fixture exceptions. The first
  scan's three deliberate redaction-fixture findings were reviewed before adding
  those exceptions; no path-wide suppression was used. Ignore checks pass for
  credentials, backups and generated files.
- Compose validation passes using generated private inputs. A guarded disposable
  container build/start/recreation/volume-restore harness and CI image audit are
  written, but their runtime branches have **not executed** without Docker.
  Registry HTTP 200 metadata is recorded separately from runtime/audit evidence.
- The user confirmed no Git remote or deployment target. No external SMTP/log,
  remote CI, model-provider, public certificate or container success is claimed.

Current detail and external prerequisites: `CONTINUATION_VERIFICATION.md`.
Older phase-specific counts below describe their execution time.

October 17 follow-through: all four selected upstream filesystem scans completed.
The new Nginx base reports zero high/critical; Python Trixie reports 44 high and
FalkorDB reports 36 high. The evaluated PostgreSQL Trixie base reports 85 high and
two critical findings. The definition now uses an Alpine 18.6 non-root derivative
with the unused Go helper removed; actual build/runtime and final-image audits
remain unexecuted. The Alpine inventory's declared OS and initial SPDX coverage
limits are explicit in the image review. A fresh production-only native venv
installs 40 packages and imports the real production API successfully. No image
findings were suppressed or treated as clean after a timeout.

## Executed
- `uv run ruff check api tests scripts migrations`: passed.
- `uv run pytest -q`: **81 passed** against a real isolated PostgreSQL 18.6
  database and the real FalkorDBLite graph engine. Tests include session auth,
  Argon2id hashing, CSRF/origins, expiry, disabled accounts, RBAC and membership,
  audit mutations, real ingestion/search/evidence, incremental graph diffs,
  historical snapshot preservation, GitHub API fixture pagination/rate limits,
  prompt-boundary policy and provider/citation failure fallback.
- `npm --prefix app run build`: TypeScript + production Vite build passed.
  Cytoscape is loaded separately; initial JS ~386 kB, graph chunk ~447 kB
  before compression. Fonts are self-hosted.
- `npm --prefix app audit --omit=dev`, `npm audit`: no reported vulnerabilities.
- Impeccable mechanical frontend detector: no findings.
- `uv run python -m scripts.verify-live`: **passed** over actual HTTP requests,
  real public GitHub clone, external durable worker, real PostgreSQL/FalkorDB,
  symbol search, exact source excerpt, no-model retrieval and logout protection.
  See `LIVE_VERIFICATION.json`: 50 files, 115 functions, 196 nodes, 319 edges,
  5.18 seconds end-to-end on this host. This is one observation, not an SLA.

## Browser verification
Three Playwright journeys are defined; the original two sequential journeys passed against the actual running services:
- User signup, empty dashboard, public repository connection and progress, graph,
  known-symbol search, source URL/excerpt, neighbors, responsive overflow, context,
  impact, diagnostics, settings/theme, admin denial, logout denial and valid/invalid login.
- Admin CLI bootstrap, browser login, live role grant/revocation enforced on an
  existing test session, jobs, audit and database readiness.

The initial missing Playwright browser was an environment failure; installed
Chrome was used. Two overlapping early runs collided in the trace directory and
are recorded as failed attempts. Accessible label gaps were fixed. Sequential
runs passed after correction. Current captures disable transitions; mobile source
focus and edge filtering are also being exercised for the visual review fixes.

An independent review found graph readability, edge filtering, mobile source
access, text contrast, an unnecessary type eyebrow and missing formal direction
metadata. Changes were implemented as one batch; the reviewer scored all six fixes resolved, with ship limited to that fix list. This review covers captured surfaces, not overall production readiness.

## Performance and dependency checks
20 authenticated fixture sessions made 200 real HTTP symbol searches with 200
correct results. p50 **136.51 ms**, p95 **784.65 ms**, elapsed 2.079 s. API RSS was
34.29 MiB before and 82.77 MiB after; these are samples, not peak memory. API CPU
consumed 1.89 s. Registration throughput and large repositories were not measured.
See `PERFORMANCE.json`. The Python production dependency audit reported no known
vulnerabilities (`DEPENDENCY_AUDIT.json`); npm audits likewise reported none.

## Not yet proved / incomplete
- Docker/Compose startup, container restart persistence and production image build:
  Docker daemon is absent on this host. Official image tags/configs and standalone
  Compose config validation passed; container execution remains unverified. Native
  PostgreSQL and FalkorDB shutdown/restart persistence and API reconnection passed
  (`PERSISTENCE_VERIFICATION.json`).
- Successful external live GitHub log download. Metadata sync is now verified in HISTORY_VERIFICATION.json. Log archive/redaction/retention
  now pass recorded fixtures and the isolated browser test. The live unauthenticated
  failed-job log probe returned HTTP 403; no successful download is claimed.
- Live configured LLM synthesis (no provider supplied); deterministic retrieval
  works, failure behavior is tested, but a successful provider response needs an
  integration test with a real OpenAI-compatible endpoint.
- Outbound password-reset delivery with a real mail server.
- Full repository access-management E2E, worker crash/recovery stress, container backups/restore, wider security/performance regression coverage and production container audit. Branch/snapshot UI, historical source and immutable citations are now verified.

## Observed issues resolved
Live indexing of `pallets/itsdangerous` exposed repeated declaration ID collisions.
The parser now creates distinct declaration nodes, avoids ambiguous resolution,
respects shadowed names, and includes a regression test. Re-running live ingestion
passed. Graph snapshots prevent partial index publication.

## Current limitations
Only Python has semantic parsing. Dynamic dispatch, star/local imports, runtime
mutation and external package relationships remain unverified. GitHub metadata
sync is bounded to four pages per resource per job; saved cursors resume subsequent
jobs. PR detail pages now resume across jobs, within GitHub’s documented listing ceilings.
Provider output is citation-ID checked, not formally fact-verified. Source data is
untrusted; the provider has no tools or command execution. Public registration
and local development are not a claim of production security readiness.

## Review and current captures
The independent finish reviewer scored all six requested fixes resolved. That
verdict covers those fixes on the supplied desktop/mobile/graph/settings/admin
captures; it does not certify every route, full requirements or production safety.
The final E2E also verifies edge filtering and mobile source scroll/focus, with a
separate mobile-source screenshot. Formal design metadata is retrospective and
preserves the unapproved working-assumption status.

## Native service recovery
PostgreSQL and owned FalkorDB were shut down/restarted; committed relational and
graph probes survived, and API readiness reconnected. A separate 3-second
PostgreSQL outage left the external worker alive with the same PID; it indexed
a new real fixture job after recovery. See `PERSISTENCE_VERIFICATION.json` and
`WORKER_RECOVERY.json`. These observations do not prove Docker volume recovery.
Standalone Compose 2.39.4 `config --quiet` passed with validation-only inputs.
GitHub Actions now defines backend, frontend and real-service E2E jobs; the remote
workflow has not been executed because this new repository has no remote.

## Branch/snapshot and log archive regression

The current backend suite passes 64 tests on real PostgreSQL/FalkorDB. Added checks
cover two real Git branches, old source after replacement, selection without global
branch mutation, historical/read-only/outsider access, mismatched snapshot IDs,
branch-scoped GitHub metadata and interrupted sync publication. A partial metadata
page cannot become visible through the history route before its graph is published.

The public-repository user browser journey now connects `stable`, verifies its SHA
differs from `main`, pins a saved snapshot, follows a context citation, clears node
selection without losing scope, and checks desktop/mobile layout. A separate browser
journey seeds a labeled recorded CI log in an isolated disposable database and API,
checks actual redacted evidence and a text download, and removes its own data.
The fixture proves app behavior; it does not prove external GitHub permissions.

Log unit/integration checks include credential-free redirect handling, host and byte
bounds, HTTP 410/429 behavior, secret redaction, owner-only files, PRODUCES graph
links, snapshot/branch/repository access, hashing, expiry before physical cleanup,
repeatable purge and saved conversation excerpt omission. A real GitHub request for
a failed itsdangerous job returned 403 without authentication (run 38830705597, job
116748581860, three HTTP requests). No log contents or signed URL were persisted.

Observed attempts: one test helper initially tried to register an existing fixture
account and was corrected; two accidentally overlapping pytest commands collided in
the shared test DB and were rerun sequentially; a rate-limit exception was initially
absorbed by a broad ValueError handler and was fixed. The isolated browser test
initially navigated before login completed; it now waits for the authenticated
workspace. One concurrent fixture run reported an opaque graph ResponseError;
the concurrent graph test reproduced `GRAPH.COPY failed, could not fork`. Bounded backoff for exactly that pre-copy failure now passes two concurrent repositories with six copies each; unrelated errors are never retried.
These failed attempts are not counted as passes.

## Ingestion exclusion and resource phase

Nested .gitignore scopes, explicit negation and parent-directory pruning now match
`git check-ignore --no-index` on a fixed fixture. Built-in dependency exclusions
still apply. Ignore rules fail closed above 64 KiB per file, 256 KiB total or 4,096
patterns; visited directories are bounded to four times the configured file budget.
Newly published source artifacts contain only indexed UTF-8 files. Uploaded ZIPs
remain private authoritative sources for reindexing; this pruning does not erase
the original upload.

Tests cover ignored/binary files absent from source artifacts, archive entry/byte
limits, duplicate paths, file/directory symlink escape and a Python source attempting
a filesystem write that is never executed. The live public GitHub HTTP ingestion
was rerun successfully: 50 files, 115 functions, 196 nodes, 319 edges, 6.25 seconds,
want_bytes source evidence, graph-only context and logout denial. The query budget
is also counted against actual graph calls for CI-log context; no duplicate artifact
lookup is hidden from the diagnostic count.

## Native backup/restore drill

`uv run python -m scripts.verify_restore` passed. It is guarded to this workspace's
owned development stack (PostgreSQL loopback 55432, FalkorDBLite 56379, exact API
and worker process commands). It creates a disposable reference repository, stops
writers, backs up PostgreSQL with pg_dump, saves/copies RDB, archives source/input/log
files with owner-only backup permissions, and records SHA-256 digests.

It restores into a new fixed-prefix database, separate real graph instance/socket
and artifact directory. Actual HTTP login succeeds against the restored API;
snapshot IDs, node counts, known graph entity and exact normalize source excerpt
match. Original services are restarted; temporary restore services/data and probe
records are removed. A private backup remains in the ignored .data/backups tree.
`RESTORE_VERIFICATION.json` records the result and digests. Container restore is
still unverified.

## Ownership and monitoring phase

The backend suite now passes 64 tests. Added checks prove ownership transfer
changes real owner/membership state, removes old-owner access when requested,
rejects disabled recipients/ordinary users, keeps admin source membership explicit,
and records audit events. Admin cancellation/retry is exercised without granting
source access. Worker upserts and recent/stale/stopped observations are checked
against PostgreSQL. API exceptions return security headers and a safe message;
exception text is absent from application logs and the error counter increments.

The admin browser journey now grants/revokes read access with enforcement on an
existing receiver session, transfers ownership, confirms the previous owner loses
write access, and captures mobile access controls plus measured health diagnostics.
A stale account-selector query was found during the journey and now polls while
access management is open. Ambiguous fixture names/selectors were made unique and
semantic. The ownership form clears its completed target.

A new worker with heartbeats survived the native three-second PostgreSQL outage
with the same PID and indexed after recovery. An accidentally concurrent admin
bootstrap failed during that intentional outage; maintenance scripts now refuse
to run while workspace Playwright tests are active. The serial browser run passed.
Request/graph-read timings are bounded process-local observations, not distributed
SLAs. Storage scans are bounded/cached and report incomplete reads explicitly.

## Durable log policy configuration

Migration 0006 stores only three allowlisted integer settings, with updater/time
and an audit event. GET/PUT administration APIs enforce current admin role, strict
bounds, forbidden extra fields and CSRF/origin protections. Tests change policy,
read it from a fresh Python process, verify zero downloads makes no external
request, and verify new expiration changes while prior artifacts keep their
original expiry. Per-process overrides refresh within five seconds.

The isolated CI log browser journey now logs in as its own fixture administrator,
sets retention/download policy, saves it through the real API and verifies the
stored result. This does not modify the development application's policy. The
current backend suite passes 64 tests; normal user/admin browser journeys remain
part of the sequential regression run.

## Current ingestion, history, retrieval and lifecycle verification

The latest complete backend run passes **64 tests** (10.51 s, real isolated
PostgreSQL/FalkorDB). Ruff passes. The production frontend builds with initial JS
385.81 kB and a separately loaded graph chunk of 447.35 kB before compression.
The manual Impeccable detector reports no findings.

The current sequential browser regression passes **three journeys in 48.4 s**,
including authorized recent questions/CI failures, archived evidence/download,
durable log policy, owner-confirmed removal with an actual isolated worker,
public repository main/stable snapshots and administrator enforcement. Desktop
and mobile captures of recent workspace content and removal were inspected.
A full-page capture initially placed an offscreen fixed skip link in the image
when captured while scrolled; captures now scroll to the top, wait for layout,
and explicitly assert that the link is outside the viewport until focused.

One intervening regression had two blank-page failures. The long-running Vite
server returned an empty cached Admin module (163 bytes, sourcemap only) after a
file rewrite. The freshly started isolated Vite server and production build worked.
Restarting the affected main development Vite server fixed the module cache, and
the same unweakened three journeys passed. These failures are not counted as passes.

Ingestion tests cover both declared and actual chunked request budgets, real
multipart spooling cleanup, AST node/declaration limits, graph-size rejection
before any write, ambiguous import handling and a 1,000-test call graph. Parser
version is python-ast-3; cache invalidation is explicit.

History tests preserve immutable commit details when sparse PR commit lists arrive,
resume PR detail pages beyond 100 records across jobs, refresh changed PR file
relationships and prove source indexing cannot publish interrupted staging rows.
Commit file pages have independent progress, resume after an actual worker
rate-limit deferral and skip completed immutable detail reloads. GitHub responses
stream under a 5 MB/20-second budget; retries count toward the 200-request ceiling.
GitHub API ceilings remain: PR listings expose at most 250 commits and 3000 changed
files. They are disclosed as incomplete for larger histories; no complete larger-PR
claim is made. Matching log links require an exact pytest node ID and matching
workflow/source commit. Bare names, other revisions, ambiguity and corrupt content
produce no association. Links mean log-reported failures; ingestion never reruns tests.

Nine fixed retrieval tasks pass, with measured latency, exact graph-call accounting
and context bytes in `RETRIEVAL_BENCHMARK.json`. Tasks cover direct symbol, callers,
dependency chain, issue→PR/commit, PR files, workflow→log→test, abbreviated SHA,
filename, missing evidence and an additional outsider isolation check. There is no
model prose. The user explicitly selected graph-only mode with no model available.
Actual model synthesis and model-behavior prompt injection are unexecuted optional
provider integration checks, not substituted with a fake successful model result.

The latest public HTTP clone/index/search/evidence/logout run passed in **5.18 s**:
50 files, 115 functions, 196 nodes/319 edges; want_bytes source, graph-only context,
11 actual graph reads and logout protection. The new 20-session load baseline
passes 200/200 correct requests, p50 **87.96 ms**, p95 **143.41 ms**, 0.931 s elapsed,
API RSS samples 96.13→99.79 MiB and 1.21 s API CPU (`PERFORMANCE.json`). These are
warm native small-fixture measurements, not large-source or production SLAs.

Migration 0007 adds durable snapshot retirement/purge markers. Fault tests show
retirement commits before storage deletion, interrupted cleanup resumes, current
heads/conversation pins survive, shared source trees survive, unique retired trees
are removed, active readers defer maintenance and retired links return 410. Owner
removal denies readers/writers/outsiders, immediately hides source access, survives
a storage failure and retries to completion. Metadata/graph/artifact/input removal
and audit retention are checked; authoritative local directories remain intact.
Compose now explicitly fixes GP_DATA_DIR=/data for API/worker so a development .env
cannot move artifacts outside the mounted volume. Container execution is unverified.

## Final local audit checks

The complete suite passes **64 tests in 13.20 s**. Added real-process crash checks
prove that a live worker lease cannot be stolen, killing its connection leaves a
durable running job, expiry permits a replacement to complete, and the previous
worker cannot checkpoint publication. Real Git rename/deletion and interruption
leave the previous graph/source/manifest intact, clean unpublished artifacts and
succeed on retry. A simulated commit that succeeds before losing its acknowledgement
preserves the published graph and exact source; cleanup first checks SQL publication
and defers if that state is unknown. Source links now URL-encode special Git filenames.

A separate subprocess imports the actual production profile and tests HTTPS session
cookies (Secure, HttpOnly, SameSite), HSTS/security headers, cookie withholding over
HTTP, disabled public API docs and disallowed-origin/CORS writes. This is an actual
production configuration test using HTTPS TestClient, not a deployed TLS test.

Actual GitHub metadata verification passed (`HISTORY_VERIFICATION.json`):
Hello-World/master, 25 external requests, 177 entities (120 PRs, 43 issues,
10 commits, 4 workflow runs), 114 PR details still pending and explicit page coverage
warnings. No logs were downloaded. The worker removed the owned disposable repo.

A labeled 400-file/4000-function capacity fixture passed through real HTTP, worker,
PostgreSQL and FalkorDB: 4402 nodes, 8001 edges, 3600 resolved calls and a bounded
80-node initial graph response. Source evidence and durable removal passed.
`CAPACITY_VERIFICATION.json` records 1.08 s, 0.57 s worker CPU, 105.10 MiB before
and 106.03 MiB sampled peak RSS. The first sampler accidentally selected the uv
launcher; that observation was discarded and the actual Python worker was measured.
Graph-process CPU is outside the reported worker sample.

The current-schema native backup/restore drill was rerun successfully; a second
private backup remains ignored. Final scope and external gates are mapped in
`REQUIREMENTS_AUDIT.md`. Rootless Docker was investigated: namespaces and subordinate
UID ranges exist, but required newuidmap/newgidmap helpers are absent. Passwordless
sudo is unavailable. Neither system security settings nor permissions were bypassed;
actual container verification still requires an available runtime.

The final browser run passed all three journeys in 48.4 s, including tablet empty workspace and an actual missing-repository error/retry. Generated main-environment accounts/repositories were removed; the app starts with an empty real workspace. A stale manually launched fixture Vite process was found and stopped. The fixture now refuses occupied ports so it cannot silently reuse another server.

After enforcing exclusive fixture ports, the focused archive/configuration/removal browser journey passed again in 11.3 s against newly started fixture servers. Both fixture ports were closed afterward. Final native readiness reports PostgreSQL and FalkorDB connected; the main workspace contains zero generated accounts/repositories.
