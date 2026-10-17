# GraphPilot continuation — October 16, 2026

October 17 local follow-up: **110 tests passed in 15.58 s** (81 application cases
plus 29 release-gate cases); Ruff/Actionlint and six-service Compose config pass.
CI now enforces full hashed Python-lock and both npm-lock audits, retains sanitized
image package/vulnerability JSON and refuses missing or incomplete scan evidence.
Fresh dependency audits report zero known vulnerabilities. The image gate was
verified with synthetic failure cases, a real config-only rejection and parser
checks on existing upstream scan reports. No actual container execution or new
image scan is implied. Details: `RELEASE_GATE_VERIFICATION.json` and README.

Latest image follow-through: October 17 local time. Native verification is complete
at this scope; actual container/public-deployment checks and image finding
remediation remain open. PostgreSQL's current Alpine filesystem scan timed out;
its publisher-declared-OS inventory is a separate result.

The independent local continuation work is implemented and verified. Full
container/public-deployment gates remain open. The user confirmed there is no Git
remote or deployment target yet. Graph-only mode remains selected; unrelated host
inference processes and the Devin coding model were not used as app providers.

## Executed checks

| Check | Result and scope |
|---|---|
| Backend | 81 passed in 15.75 s on real isolated PostgreSQL/FalkorDB; one upstream TestClient deprecation warning |
| Browser | Three real-service journeys passed in 49.6 s after restarting the updated API/worker; generated main-app accounts/repositories removed |
| Frontend | TypeScript/production build passed; initial JS 385.81 kB, separate graph chunk 447.35 kB |
| SMTP | Six actual loopback SMTP cases; authenticated STARTTLS delivery and five failures. Targeted SMTP/auth run: 12 passed in 1.58 s |
| HTTPS | Real native Nginx 1.28.3, built frontend, production API/worker and disposable real DB/artifacts; ephemeral locally trusted certificate |
| Lint | Ruff and Actionlint 1.7.12 passed; downloaded Actionlint checksum verified |
| Compose | Configuration validation passed with generated private inputs; no container execution |
| Registry | Six image manifests returned HTTP 200; metadata is neither execution nor a vulnerability audit |
| Candidate secrets | Gitleaks passed with exact exceptions for invalid redaction fixtures; credentials/backups/build outputs excluded |
| Dependencies | Complete exported lock, including new dev SMTP dependencies, passed pip-audit with no known vulnerabilities reported |

Evidence: `GATEWAY_VERIFICATION.json`, `SMTP_VERIFICATION.json`,
`CONTAINER_VERIFICATION.json`, `IMAGE_METADATA_VERIFICATION.json`,
`REPOSITORY_VERIFICATION.json`, `CONTINUATION_DEPENDENCY_AUDIT.json`.

## Corrections and scope

Reset mail now uses a verifying SSL context. Real transactions reject missing
STARTTLS, untrusted certificates, wrong hostnames, rejected credentials and
rejected delivery. Failures preserve the prior token/session and expose a safe
error. Success proves the actual envelope, reset link, one-time token and session
revocation without retaining tokens in reports. External inbox delivery is absent.

Production requires a valid HTTPS public origin among the allowed origins. URL
validation rejects paths, credentials, queries, fragments and invalid ports.
Swagger, ReDoc and schema routes are disabled in production; development routes
use `/api/`. Configuration errors and representations omit credentials, with a regression test for startup validation failures. Nginx refreshes Docker DNS, replaces caller-supplied forwarding
addresses, rejects bare `/api` and adds `object-src 'none'`. The container API
trusts its private gateway. The eventual outer TLS proxy needs explicit trusted
real-IP ingress configuration before per-client auth limits can be relied upon.

Recursive env/bytecode exclusions and ignored backups protect build/Git candidates.
CI readiness now has mandatory final checks. New CI jobs scan candidates and run
the owned container build/start/recreation/volume-restore harness plus image audit.
Only configuration validation has executed for that harness. Runtime branches
must be exercised and corrected as necessary when Docker is supplied.

The native gateway probe verifies JavaScript MIME, certificate trust/rejection,
Secure/HttpOnly/SameSite cookies and withholding over HTTP, CSP/CORS/CSRF, both body
limits, worker indexing, exact source, outsider denial, API downtime/recovery,
session/source persistence and completed owned removal. Its data/processes/key
are removed. This does not prove public certificate issuance or containers.

SWE-2 Max through the authorized Devin CLI performed a bounded read-only review.
Its PostgreSQL volume-path finding was rejected after checking the actual 18.6
image: the volume is `/var/lib/postgresql`, with PGDATA underneath `18/docker`,
matching Compose. The [official PostgreSQL 18 Dockerfile](https://github.com/docker-library/postgres/blob/master/18/bookworm/Dockerfile)
and anonymous registry configuration support this. Other concrete deployment
findings were checked and fixed.

The first Gitleaks scan flagged three deliberate test strings. Exact exceptions
for the invalid AWS-looking value and non-key private-key block resolved these;
no whole-file/path exception was added. Failed patch applications changed no
files. No executed backend/browser regression failed in this continuation.

An additional SWE-2 Max read-only verification-script review produced no final
response after 17 minutes and was stopped by its exact process/child scope. It is
not counted as a completed review or a passing check. The scripts received a local
code review and reject optimized Python so their assertions cannot be disabled.

## Remaining prerequisites

1. Docker Engine/Compose: no runtime/socket or `newuidmap`/`newgidmap` exists here;
   passwordless sudo is unavailable. No host security settings were bypassed.
   Container runtime, private networking, volume restore and image audit are open.
2. Git remote/organization/visibility and hosting/domain/TLS destination. The user
   confirmed none yet. Source remains untracked; no commit/publication/remote CI
   success or public certificate was invented.
3. SMTP service and designated inbox for external delivery; configuration is empty.
4. Authorized backend GitHub credentials for external CI-log success; no token is
   configured. Prior metadata/recorded archive evidence stands; live log probe was 403.
5. A real endpoint/model only if the user changes graph-only mode. Real synthesis
   and model-behavior injection evaluation remain optional/unexecuted.

## Commands

```bash
uv run pytest -q
uv run ruff check api tests scripts migrations
npm --prefix app run build
PLAYWRIGHT_CHANNEL=chrome npx playwright test
uv run python -m scripts.verify_gateway --nginx /path/to/nginx
uv run python -m scripts.verify_compose --check-config
uv run python -m scripts.verify_repository --gitleaks /path/to/gitleaks
# Requires Docker; creates/removes only its own disposable deployment:
uv run python -m scripts.verify_compose
```

Primary changes: `api/auth.py` (verifying STARTTLS), `api/config.py` (URLs and
credential-safe errors/representations), `api/main.py` (production documentation
cleanup), `tests/test_smtp.py`, `tests/test_production.py`, the three Dockerfiles,
Compose/CI definitions, and the new gateway/Compose/repository/image verification
scripts. Source schema and graph-only application behavior are preserved.

The normal native stack remains running. The original requirement file is unchanged.

## Image follow-through — October 17 (local time)

Actual daemonless image scans exposed stale-image findings, leading to maintained,
digest-pinned Nginx/Trixie definitions and a small non-root PostgreSQL derivative.
The replacement Nginx base has no high/critical findings; the Python Trixie base
has no critical and 44 high findings. Full image/running-container verification
and residual-finding remediation remain open. Publisher inventories were checked
against the pinned digests; their OS-package coverage is missing and is reported
explicitly. See `IMAGE_SECURITY_REVIEW.md` and the raw JSON reports. Earlier registry
timeouts were not passes; the longer FalkorDB scan completed. The current Alpine PostgreSQL filesystem scan still timed out. No production-ready or
vulnerability-free claim is made for the final application images.
