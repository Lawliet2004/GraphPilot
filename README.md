# GraphPilot

Evidence-aware code intelligence with **FalkorDB**, FastAPI, PostgreSQL and React.
Connect a repository, build its real static graph, explore dependencies and inspect
source evidence. Deterministic search works without an LLM or paid account.

**Native and container checks pass.** Repository exploration, evidence, history and
administration have real database, HTTP and browser checks. Local Docker and remote
CI verify startup, private networking, restart and volume backup/restore. All four
CI runtime images report zero known vulnerabilities at the recorded scan time.
Public hosting/HTTPS and external email delivery remain to be configured.
See [implementation status](IMPLEMENTATION_STATUS.md), [test report](docs/TEST_REPORT.md) and [interface review](docs/UI_REVIEW.md)
and the [requirement-by-requirement audit](docs/REQUIREMENTS_AUDIT.md).

## Free cloud demos and MCP

The complete stack can be started in a GitHub Codespace using the included dev
container and `python3 scripts/cloud_demo.py start`. It keeps isolated private
configuration and persistent volumes, and uses the forwarded HTTPS origin.
Codespaces has a finite free allowance and idle shutdown; it is for scheduled
demos, not permanent hosting. The first public cloud deployment is verified;
see the cloud report for its URL, checks and remaining account setup.

Optional read-only MCP tools use expiring per-user bearer credentials at
`/api/mcp/`; existing repository permissions apply. No model or paid API is needed.
A stdio client bridge, an optional QA agent profile and read-only deployment
checks are included. See the [cloud demo, MCP and QA guide](docs/CLOUD_DEMO.md)
and [implementation plan](docs/CLOUD_PLAN.md).

The [GitHub account and CLI guide](docs/GITHUB_AND_CLI.md) covers selected private
repositories and browser-approved command-line access. Live GitHub access needs
the operator's App registration and installation. The [student hosting runbook](docs/AZURE_HOSTING.md)
describes the always-awake deployment pending Azure academic verification.

## What works now

- Argon2id registration/login, hashed expiring sessions, HttpOnly cookies, origin
  and CSRF checks, logout/revocation, disabled accounts and optional reset email.
- Backend repository membership and read/write enforcement, protected admin role
  changes, account disabling, access grants/revocation, job retry and audit logs.
- Public GitHub, explicitly allowed server-local Git and bounded source ZIP ingestion.
  Indexing never imports or executes repository code. Hooks, submodules, checkout
  filters and external Git protocols are not used.
- Durable PostgreSQL jobs with leases, bounded attempts, cancellation checkpoints,
  exclusive claims, repository advisory locks and stale-worker publication fencing.
- Python file/class/function/test entities, static CALLS/IMPORTS/DEFINES/TESTS edges,
  stable scoped IDs, source references and immutable graph snapshot publication.
- Incremental hashes skip parsing unchanged files; FalkorDB graph copies receive
  node/edge diffs. Stale active edges disappear; prior graph snapshots remain intact.
  A completely unchanged scan does no graph writes.
- Bounded graph visualization, search/filter/zoom/pan, neighbor expansion, keyboard
  node list, source excerpts, direct/indirect impact and bounded path API.
- GitHub metadata sync for commits, issues, PR references/files and workflow failure
  metadata. Stable IDs, page cursors, rate-limit deferral and coverage warnings.
- Context search, source citations, conversation history and retrieval diagnostics.
  Optional OpenAI-compatible model synthesis with no tool or shell access; failed
  provider calls or unknown citation IDs fall back to genuine graph evidence.
- Responsive landing, auth, repositories, connection, graph, overview, context,
  timeline, impact, diagnostics, settings, activity and administration screens.
  Light/dark/system preference and self-hosted fonts.

## Start with Docker Compose

Requires Docker Engine + Compose v2. No databases need public host ports.
Docker Engine 29.1.3, Compose 2.40.3 and Buildx 0.30.1 are installed on the
development host. The disposable container drill passes locally and in remote CI;
see [container evidence](docs/CONTAINER_VERIFICATION.json).

```bash
cp .env.example .env
chmod 600 .env
```

Edit `.env` and set your own strong `POSTGRES_PASSWORD`. Set the same password in
`GP_COMPOSE_DATABASE_URL`, URL-encoding it when necessary. Use the `postgres`
hostname in that DSN. Set the browser origin and public URL for the address you
will actually open:

```dotenv
GP_ORIGINS=["http://localhost:8080"]
GP_PUBLIC_URL=http://localhost:8080
```

The password must be supplied by you; no default administrator or database
password is shipped. Keep development `GP_DATABASE_URL` for native commands,
or set it to the appropriate host connection when needed.

```bash
docker compose up --build -d
docker compose ps
curl --fail http://localhost:8080/api/health/ready
# Open http://localhost:8080 and create an account.
docker compose exec api python -m api.cli create-admin you@example.com
# The bootstrap command prompts for a password, never a command-line secret.
docker compose logs -f api worker
docker compose down
```

`migrate` applies Alembic migrations before API/worker startup. PostgreSQL,
FalkorDB and source artifacts have durable named volumes. `docker compose down`
preserves them; `down -v` would delete them. Database services have no published
ports and use an internal network; only the web gateway binds host loopback.

## Native development

Requires Python 3.12/3.13, uv 0.13.1+, Node 22.12+, npm, Git and PostgreSQL.
FalkorDB may be a regular local service or the optional real embedded engine.

```bash
uv sync --frozen
npm --prefix app ci
npm ci
cp .env.example .env
chmod 600 .env
# Configure GP_DATABASE_URL for a real PostgreSQL database.
# Optional local source access: GP_ALLOWED_LOCAL_ROOTS=["/absolute/allowed/root"]
uv run alembic upgrade head
```

Start these in separate terminals:

```bash
# Optional embedded FalkorDB, bound to loopback port 56379:
uv run python scripts/run-lite.py
# Set GP_FALKOR_PORT=56379 in .env for this option.

uv run uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload --no-access-log
uv run python -m api.worker
npm --prefix app run dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/api` to FastAPI on port 8000.
No frontend environment variable contains a service credential.

For this Ubuntu 26.04 host, PostgreSQL packages were downloaded and extracted
under the ignored `.tools/postgres` directory, without changing system services:

```bash
mkdir -p .tools/postgres
apt-get download postgresql-18 postgresql-client-18 libpq5
for archive in ./*.deb; do
  dpkg-deb -x "$archive" .tools/postgres
  mv "$archive" .tools/
done
scripts/native-postgres.sh
```

The development-only helper initializes `.data/postgres`, generates a local random
password in a mode-600 file, binds PostgreSQL to loopback port 55432 and writes
`.env` only if it does not already exist. If you copied `.env` earlier, configure
the native DSN using that generated password. It does not overwrite user settings.
This helper is specific to the downloaded Ubuntu binaries; use your normal
PostgreSQL installation on other systems.

Create an initial administrator after migrations:

```bash
uv run python -m api.cli create-admin you@example.com --name "Your Name"
```

Ordinary registration always creates a User. An Admin can see administrative
metadata, but needs an explicit, audited repository membership to read its code.

## Connect and investigate

1. Register/log in, then choose **Connect repository**.
2. Supply an exact public GitHub URL and branch, a ZIP, or a server-local Git path
   within configured allowed roots. A remote website cannot read visitor folders.
3. The external worker claims the job. Observe real status/progress on the repository.
4. Search a known symbol, select a node, expand neighbors and inspect source evidence.
5. Use impact/context/timeline tabs. GitHub history is retrieved by an explicit sync.

Archive content is bounded to 25 MB compressed, 100 MB extracted and 5,000 files
by default. UTF-8 text files up to 1 MB get file references; only Python gets
semantic entities. Local Git ingestion reads the committed branch without altering
the working tree. Uncommitted edits are intentionally not a Git snapshot.

## Model and email configuration

Set these **server-side** for local llama.cpp or another OpenAI-compatible provider:

```dotenv
GP_LLM_BASE_URL=http://127.0.0.1:8081/v1
GP_LLM_MODEL=your-model-name
GP_LLM_API_KEY=
```

A hosted provider can use an HTTPS base URL and its key. Both URL and model must
be supplied. Inside Compose, loopback addresses refer to that container; configure
a reachable service or host address. The model gets bounded quoted excerpts,
relationship data and citation IDs, never database credentials or shell tools.
When unset/unavailable, context returns structured search results and an explicit
notice. Actual successful inference with a real configured model remains unverified.

Optional [Firebase Authentication](docs/FIREBASE_AUTH.md) manages email/password
credentials, verification and password reset on the Spark plan. GraphPilot keeps
its own administrator roles and repository permissions. Existing local accounts
require explicit operator linking; email matches never grant account access.

Local password resets use configured SMTP with STARTTLS (`GP_SMTP_*`, `GP_PUBLIC_URL`).
Without email delivery the UI explains that reset is unavailable. Tests cover a
one-time token and session invalidation. Real local SMTP/STARTTLS delivery with
authentication now passes, including certificate/hostname validation and safe
failure handling. External inbox delivery remains unverified. The client uses the
system CA store; a private mail CA can be supplied through `SSL_CERT_FILE`.
`GP_GITHUB_TOKEN`, if configured, remains backend-only.
Private repository support via GitHub App is not implemented.

## Test

Start PostgreSQL and FalkorDB first. Pytest creates/uses a distinct database named
`graphpilot_test` and truncates **only that database**. The DB role must be allowed
to create it, or pre-create it and supply a suitable test DSN.

```bash
uv run ruff check api tests scripts migrations
uv run pytest -q
npm --prefix app run build
npm --prefix app audit --package-lock-only
npm audit --package-lock-only
# Start native API/worker/Vite as above before browser tests:
npx playwright install chromium
npm run e2e
# Or use an already installed Chrome:
PLAYWRIGHT_CHANNEL=chrome npm run e2e
# Real public repository HTTP verification and 20-session baseline:
uv run python -m scripts.verify-live
uv run python -m scripts.benchmark
```

Browser tests create labeled disposable development accounts in the running
application. They do not reuse your credentials. Clean generated test accounts and their repositories with
`uv run python -m scripts.cleanup-e2e` after tests; audit events remain. Screenshots/reports go to ignored
`.impeccable/review`, `test-results` and `playwright-report` directories.
GitHub Actions defines lint, real database tests, a frontend build and real-service
browser journeys. Dependency jobs audit the complete Python lock and both npm locks,
including development packages. All six jobs pass remotely: 111 backend/release
tests, three browser journeys, container verification and image/dependency/secret
audits. See [CI evidence](docs/CI_VERIFICATION.json).

Run the same Python dependency audit locally without installing audited packages:

```bash
mkdir -p .data/ci
uv export --frozen --all-groups --no-emit-project --format requirements.txt --output-file .data/ci/requirements.txt
uvx --from pip-audit==2.10.1 pip-audit --require-hashes --disable-pip --strict -r .data/ci/requirements.txt --format json --output .data/ci/python-audit.json
# Requires Docker; operates on its own disposable deployment:
uv run python -m scripts.verify_compose --output .data/ci/container.json
uv run python -m scripts.audit_container_images
```

The image gate requires full image IDs for every service and rejects incomplete
scans, missing OS/application package inventories, modified findings, end-of-life
OS versions and high/critical vulnerabilities, including those without a listed
fix. CI retains dependency and package/vulnerability JSON reports. Image environment
configuration and private scanner logs are excluded from uploaded reports. The
gate's local regression checks do not establish a passing container-image audit;
see [release-check evidence](docs/RELEASE_GATE_VERIFICATION.json).

## Architecture and files

`api/auth.py` owns authentication; `services/permissions.py` owns repository access.
`routes/` exposes the typed HTTP operations. `ingestion/` validates sources and
parses Python. `graph/store.py` is the only Cypher template boundary. `worker.py`
claims durable jobs; `services/indexing.py` publishes graph and source snapshots.
`services/github.py` ingests metadata; `search/` ranks evidence; `agent/` calls an
optional model without tools. SQLAlchemy models and frozen Alembic migrations
store metadata in PostgreSQL. React sources are under `app/src`.

See [architecture decisions and CodeGraph evaluation](docs/ARCHITECTURE.md).
No upstream code is copied. Its shared-token API is not mounted or exposed.

## Production deployment

Production verification is incomplete; finish the outstanding gates before using
sensitive repositories. Build the gateway/API images, supply secrets through
restricted deployment configuration and put an HTTPS reverse proxy in front of
the loopback gateway. Example Caddy route:

```caddyfile
graphpilot.example.com {
    reverse_proxy 127.0.0.1:8080
}
```

Set `GP_ENVIRONMENT=production`, `GP_COOKIE_SECURE=true`, exact HTTPS `GP_ORIGINS`
and HTTPS `GP_PUBLIC_URL`. Production configuration rejects insecure cookies or
HTTP origins, malformed URLs and a public URL outside the allowed origins.
Swagger, ReDoc and the schema are disabled in production; development docs and
schema live under `/api/`. Do not expose database ports. Do not commit `.env` or private source
artifacts. Restrict allowed local roots and filesystem mounts deliberately.
Gateway/API security headers and a gateway CSP are provided. Keep backups private
and encrypted; source artifacts and audit logs are sensitive application data.

The container API trusts forwarding headers from the provided gateway, which
replaces incoming `X-Forwarded-For` with its peer address. Keep the API port private.
When placing another proxy in front, configure Nginx's trusted real-IP ingress for
that deployment before relying on per-client authentication limits. The Docker
gateway refreshes service DNS so API recreation can recover without restarting web.

Local HTTPS verification now runs the built frontend through real Nginx with the
production API, worker and disposable database/artifacts. It validates a temporary
locally trusted certificate, Secure cookies, CSP/CORS/CSRF, upload limits, source
isolation and API restart recovery. It does not prove a public certificate or a
container deployment. See `docs/GATEWAY_VERIFICATION.json`.

```bash
# Supply an Nginx executable; this binds only dynamically selected loopback ports.
uv run python -m scripts.verify_gateway --nginx /path/to/nginx
# Safe configuration validation without starting containers:
uv run python -m scripts.verify_compose --check-config
# Build/start/recreate/backup/restore a disposable stack:
uv run python -m scripts.verify_compose
# Inspect only Git candidates with Gitleaks; ignored private data is never scanned:
uv run python -m scripts.verify_repository --gitleaks /path/to/gitleaks
# Public runtime-base/service scans work without Docker (large registry downloads):
uv run python -m scripts.audit_remote_images --trivy /path/to/trivy --db-repository ghcr.io/aquasecurity/trivy-db:2
```

The Compose verifier generates private credentials and its own project, ports,
volumes and environment file. It destroys only that disposable deployment. Its
actual container/restore path passes locally and in CI, including non-root database
startup and effective graph persistence/memory settings. CI includes the image
audit and a separate candidate secret scan; workflow syntax passes Actionlint.
`GP_ENV_FILE` and `GP_WEB_PORT` allow
an explicit separate Compose environment file and loopback port; normal startup
continues to use `.env` and port 8080.

Historical image scans found high/critical findings in the previous definitions.
Current images use pinned Python 3.12 Alpine, Nginx 1.30.6 Alpine, PostgreSQL 18.6
Alpine and the server-only FalkorDB 4.22.1 Alpine image. Derived images apply fixed
zlib/nghttp2 packages and remove unused runtime pip/gosu. PostgreSQL and FalkorDB
run as their database users. All four actual CI runtime images report zero known
vulnerabilities; no findings were suppressed. See the
[image review](docs/IMAGE_SECURITY_REVIEW.md) and
[built-image audit](docs/CONTAINER_IMAGE_AUDIT.json). Results describe their scan
time and do not establish a public deployment or future vulnerability status.

### Backup and restore

Stop API/worker writers to obtain a consistent metadata/graph/artifact set:

```bash
mkdir -p backups
chmod 700 backups
docker compose stop api worker
docker compose exec -T postgres sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > backups/postgres.dump
docker compose exec -T falkordb redis-cli SAVE
docker compose exec -T falkordb tar czf - -C /data . > backups/falkor.tar.gz
docker compose run --rm --no-deps -T --entrypoint python api -c 'import sys,tarfile; t=tarfile.open(fileobj=sys.stdout.buffer,mode="w|gz"); t.add("/data",arcname="."); t.close()' > backups/artifacts.tar.gz
chmod 600 backups/*
docker compose start api worker
```

Restore into an isolated deployment with matching secrets and image versions:
stop API/worker and FalkorDB, restore its volume with the service image as a tar
helper, restore artifacts similarly, and use `pg_restore --clean --if-exists` into
the destination database. Restart databases, apply migrations, then start API and
worker and check readiness, memberships, source evidence and snapshot counts.
The guarded Compose drill has verified backup/restore locally and in CI. The
manual example above is guidance; use the verifier for the executed sequence.
A separate native restore drill has passed, including actual restored login,
graph identity and source evidence; see `docs/RESTORE_VERIFICATION.json`. The
guarded native command is `uv run python -m scripts.verify_restore` and is restricted
to this workspace’s development process/port layout. It briefly stops and restarts
API/worker writers, keeps a private ignored backup, and restores only into disposable
instances.

## Troubleshooting and known limits

- **Queued jobs do not progress:** run the worker and check `docker compose logs worker`
  or its native terminal. Jobs persist across API restarts; readiness alone does
  not prove a worker is alive.
- **403 on a write:** use the configured exact browser origin and current CSRF cookie.
  For scripted API calls include `Origin` and the session's `X-CSRF-Token`.
- **Local directory rejected:** configure allowed roots on the backend; Docker also
  needs an explicit mount. Arbitrary visitor filesystem access is unsupported.
- **Missing calls:** dynamic dispatch, shadowed/ambiguous definitions, local/star
  imports and external packages are unverified. Graph edges are static evidence.
- **No AI prose:** configure a provider or use the genuine graph results as returned.
- **Missing history:** trigger GitHub sync and inspect coverage warnings/rate limits.
  Sync scans four pages per resource per job; subsequent jobs resume saved cursors.
  PR and commit file-detail pages resume from durable cursors. GitHub caps PR
  listings at 250 commits and 3000 changed files; larger histories remain incomplete.
  References do not imply issue fixes. Selected failed-job logs are downloaded when GitHub permissions allow it; inspect each workflow’s log status.
- **Storage growth:** snapshot retirement runs after indexing/history jobs, keeping
  current branch heads, conversation-pinned snapshots, and at least the latest ten
  generations per branch. Unpinned older generations become eligible after 30 days.
  Expiring CI logs have a separate periodic cleanup. Native backup/restore has been
  drilled, and container-volume backup/restore passes locally and in CI.
- **Branch selection:** connect existing Git branches from the repository header.
  Each branch has its own graph head; selection stays in the URL for that investigation.
  Snapshot selection pins graph, source, impact and conversation citations to an immutable
  generation. Saved snapshots are read-only. ZIP sources are fixed snapshots and cannot
  fetch additional Git branches. The selector lists the latest 50 generations by default;
  direct older snapshot links continue to resolve while retained.

The full remaining work is tracked in `IMPLEMENTATION_STATUS.md`; passing the
current tests does not complete all requirements in `docs/REQUIREMENTS.md`.

## CI log archives

GitHub history sync selects at most three failed jobs per workflow run and ten new
log downloads per sync. It follows the [GitHub job-log endpoint](https://docs.github.com/en/rest/actions/workflow-jobs#download-job-logs-for-a-workflow-run)
to an HTTPS GitHub storage host using a separate client without the backend token.
Redirect URLs are never saved. Each plain-text transfer is limited to 2 MB and a
20-second streaming deadline; compressed and binary log transfers are rejected.
Unavailable, expired or permission-denied logs remain explicit gaps in coverage.

Configured secrets and common credentials, tokens, private keys and credential URLs
are redacted before any file is written. This is best effort: unfamiliar secret
formats may remain. Complete logs stay outside graph properties. Log evidence and
downloads require membership, matching branch and presence in the selected snapshot.
Integrity hashes are checked on reads. The graph stores provenance and archive
metadata; saved conversations omit complete log excerpts. Model answers may retain
derived text in conversation history.

`GP_ARTIFACT_RETENTION_DAYS` defaults to 30. Expired files are denied immediately,
then deleted in batches of 100 by the worker every minute; metadata/audit events
remain. The original deadline is retained when a known job log is seen again. Run
`uv run python -m api.cli purge-artifacts` for an explicit audited cleanup batch.
`GP_MAX_LOG_BYTES` and `GP_MAX_LOG_DOWNLOADS` bound archive work; zero downloads
disables new log transfers. Source/graph snapshots use the separate policy below.

The CI log browser test uses a labeled synthetic fixture in a disposable
`graphpilot_browser_<random-id>` PostgreSQL database, its own artifact directory,
and isolated API/Vite ports 8001/5174. It exercises real storage, graph, auth,
evidence and downloads without inserting fixtures into the normal application.
The live unauthenticated GitHub log probe returned HTTP 403. A real authenticated
job-log download through the application adapter now passes for this repository;
its token was held in memory and the probe did not persist an artifact. Storage,
snapshot permissions and browser downloads are covered separately by fixtures.

Ingestion applies nested `.gitignore` files with Git-style negation and directory
pruning, in addition to fixed dependency exclusions. Ignore files are limited to
64 KiB each, 256 KiB total and 4,096 lines/patterns across the tree. Directory visits
are bounded to four times `GP_MAX_FILES`. Exceeding an ignore budget fails indexing
instead of silently retaining excluded files. Newly published source artifacts
contain indexed UTF-8 text only; original uploaded ZIPs remain private inputs for
reindexing until their separate repository lifecycle is removed.

Administrators can transfer repository ownership with an explicit previous-owner
access choice. Transfers are audited and take effect on existing sessions. Admin
job cancellation/retry does not grant implicit access to source content. System
health separates database readiness from durable worker heartbeats (every ten
seconds; stale after 45). Request/error and graph-read p50/p95 metrics cover only
the current API process and its last 2,000 samples. File storage counts cover
source artifacts, uploads and CI logs with a 30-second cache and bounded scan;
PostgreSQL size is measured separately. These observations do not certify job
completion, security or a performance SLA.

Administration → configuration provides durable, audited CI log retention, new
download count and maximum byte controls. Values apply to new archives/transfers
within five seconds in each worker. Existing archived files retain their original
expiry. Set downloads to zero to disable new transfers. These three overrides
are stored in PostgreSQL; provider credentials, allowed local roots and database
configuration remain server environment settings.


## Source snapshots and removal

`GP_SNAPSHOT_RETENTION_DAYS=30` and `GP_SNAPSHOT_KEEP_PER_BRANCH=10` protect recent
history. Current branch heads and snapshots cited by saved conversations are retained
regardless of age. After a source/history job, cleanup retires at most 100 eligible
snapshots and purges at most 100 already-retired generations. Retirement is committed
before deleting graph/source data; interrupted cleanup is safe to retry. Retired
links return HTTP 410. Small retirement metadata and audit records remain. A source
tree shared by another retained snapshot is preserved. Conversation pins can extend
storage lifetime, so this is an age/count policy rather than a strict disk quota.

Run `uv run python -m api.cli prune-snapshots REPOSITORY_UUID` to apply another
configured batch. Maintenance defers while an index or evidence reader holds its
repository/storage lock. The same PostgreSQL-backed locks coordinate API/worker
processes sharing the artifact volume.

Repository owners can expand **Overview → Remove repository**, type its exact name,
and request permanent removal for all members. Active jobs must finish or be
cancelled first. Access disappears immediately; a durable removal job deletes only
that UUID's graphs, stored source trees, logs, original uploaded ZIP, conversation
and repository metadata. Original server-local Git directories remain untouched.
Audit records remain. Confirmed removal cannot be cancelled. Failed cleanup stays
hidden from ordinary source access and can be retried by the owner through the same
DELETE API, or by an administrator from the job list.

Requests are bounded before JSON/multipart parsing: 64 KiB for ordinary bodies and
configured ZIP bytes plus 64 KiB multipart overhead for uploads, including chunked
requests. Python AST parsing is limited to 50,000 AST nodes, 2,000 declarations and
10,000 calls per file. Graph publication is limited to 50,000 entities and 200,000
relationships. These are capacity limits, not claims of complete runtime analysis.

Recent queries are private to their author and require current repository membership.
The workspace's CI summary reads at most ten authorized latest branch heads and states
that coverage. Context retrieval recognizes issue/PR numbers, filenames, commit SHA
prefixes and dependency/CI questions. Exact pytest failure node IDs are associated
with a TestCase only at the indexed commit, with explicit log provenance; tests are
not rerun by ingestion.


Verification commands beyond the test suite:

```bash
uv run python -m scripts.verify_history    # Real public metadata sync; cleans its own probe
uv run python -m scripts.verify_capacity   # Labeled synthetic sources, real HTTP/worker/DBs
```

`docs/HISTORY_VERIFICATION.json` records successful real GitHub metadata sync.
`docs/CAPACITY_VERIFICATION.json` records 400 files, 4000 functions, 4402 nodes and
8001 relationships, with an 80-node initial graph response. The 1.08-second native
observation used 0.57 s worker CPU and a 106.03 MiB sampled worker RSS peak; it
excludes separate graph-process CPU. These are baseline observations, not SLAs.
