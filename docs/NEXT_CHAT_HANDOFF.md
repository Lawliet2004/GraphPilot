# GraphPilot current handoff — October 17, 2026

Repository: https://github.com/Lawliet2004/GraphPilot, branch `main`.
The user explicitly authorized initialization, commits and pushes under their own
identity. Author and committer are `Lawliet2004
<168631200+Lawliet2004@users.noreply.github.com>`, with no extra co-authors.
Do not introduce an agent author/co-author or another branch.

## Latest continuation — free local HTTPS testing

Oracle signup was rejected during card verification. The user authorized switching
to a Cloudflare Quick Tunnel on this computer. The isolated Docker demo and tunnel
are running; public browser/authentication verification is still pending.

**Read the local ignored `.data/quick-tunnel/HANDOFF.md` before continuing.** It
contains current runtime state, controller commands and the remaining checks. Its
hosting status supersedes the older hosting-deferred notes below. Do not commit
private credentials, tunnel logs or other ignored operational files.

## Current verified result

- All six remote CI jobs pass: **111 backend/release tests**, **three browser
  journeys**, dependency/secret checks, frontend build and actual container drill.
- Four actual CI runtime images report **zero known vulnerabilities** at scan time.
  Read `CI_VERIFICATION.json` and `CONTAINER_IMAGE_AUDIT.json` for commit/run/IDs.
- Docker Engine 29.1.3, Compose 2.40.3 and Buildx 0.30.1 are installed and running.
  Local Compose build/start/private networking/non-root database initialization,
  indexing, API recreation and SQL/graph/artifact volume backup+restore pass.
  The disposable deployment/volumes were removed. See `CONTAINER_LOCAL_VERIFICATION.json`.
- Current definitions use Python 3.12 Alpine, Nginx 1.30.6 Alpine, PostgreSQL 18.6
  Alpine derivative and server-only FalkorDB 4.22.1 Alpine. Explicit graph startup
  is checked for `/data`, AOF, 768 MiB and noeviction. Global runtime pip/gosu are
  removed; fixed zlib/nghttp2 packages are required. See `IMAGE_SECURITY_REVIEW.md`.
- The containerized safe Git adapter fetches this real repository over HTTPS.
  An independent non-root graph-container backup/restore probe also passes.
- Actual authenticated GitHub job-log download through the production adapter
  passes using the current account credential in memory. No token was saved to
  project configuration; this particular probe did not persist an archive.
- Authenticated loopback SMTP/STARTTLS and native Nginx HTTPS tests passed earlier.
  Their certificates/inbox scope is local, not a public deployment.

## Accepted scope and remaining prerequisites

The user explicitly deferred hosting/domain setup. A deployment target, domain and
TLS configuration are needed for public HTTPS verification. An SMTP service and
designated inbox are needed for external mail delivery. Continuous authenticated
GitHub integration in a deployed app needs its own server-side credential setup;
local CLI credentials were not copied into `.env`.

**Keep graph-only mode.** No application model/endpoint was provided and no LLM is
required. Do not confuse a coding-agent model or unrelated host process with an
application provider. The app implementation and current local/container/remote CI
checks are complete at this scope; public deployment is not claimed.

The user explicitly requested Devin subagents using the exact `swe-2-max` model.
The CLI is available as `devin --model swe-2-max`; respect normal permission and
workspace-trust checks. Recent delegation was read-only: container correctness and
release-documentation reviews. Parent verification remains authoritative.

## Workspace and safe operation

Workspace: `/home/papan/Desktop/Projects/GraphPilot`. Read `README.md`,
`IMPLEMENTATION_STATUS.md`, `REQUIREMENTS_AUDIT.md` and `TEST_REPORT.md` first.
The original `REQUIREMENTS.md` is unchanged; SHA-256:
`74852d1e4c9d338a76d93d19569e1cf66082fe064ce2f75cef0a556686314cc0`.

The normal native app remains on loopback API8000/Vite5173, PostgreSQL55432 and
FalkorDBLite56379 with its own durable worker. Discover owned PIDs before any
restart; do not kill unrelated processes. Never print `.env`, keyring credentials,
signed storage URLs or backup contents. `.data`, `.tools`, backups, node_modules,
build outputs and local review logs are ignored. No default admin is shipped.

Pytest uses and truncates only `graphpilot_test`. **Do not run concurrent pytest
processes**, or overlap intentional native DB outages/restore drills with tests.
The container verifier creates its own random project, private credentials, port
and volumes; it never uses normal `.env` or native databases. Docker membership
was added to the current user; an older terminal can use `sg docker -c 'COMMAND'`
or start a new group/login session. Do not change host security policies.

Useful commands:

```bash
uv run ruff check api tests scripts migrations
uv run pytest -q
npm --prefix app run build
PLAYWRIGHT_CHANNEL=chrome npx playwright test
uv run python -m scripts.verify_compose --output .data/ci/container.json
uv run python -m scripts.audit_container_images
uv run python -m scripts.verify_repository
```

Earlier reports contain dated historical 64/81/110-test counts, failed or limited
upstream scans and an unauthenticated GitHub 403. Current CI/container/image reports
supersede those release-state claims without rewriting the old observations.
