# GraphPilot implementation and verification status

The unchanged specification is in `docs/REQUIREMENTS.md`. The native application,
container deployment path and remote CI are verified. The repository is published
on `main` at https://github.com/Lawliet2004/GraphPilot under the user's own identity.
Hosting/domain setup is explicitly deferred; public HTTPS and external SMTP inbox
delivery remain unverified. Graph-only mode remains selected.

## Current evidence

- **111 backend/release tests and three browser journeys pass in remote CI.**
  All six jobs pass; see `docs/CI_VERIFICATION.json` for the exact commit/run.
- Actual local and CI image builds/startup, migrations, private networking,
  non-root PostgreSQL/FalkorDB initialization, indexing, source authorization, API
  recreation and SQL/graph/artifact volume backup+restore pass. Owned deployments
  and volumes were removed. See `docs/CONTAINER_LOCAL_VERIFICATION.json` and
  `docs/CONTAINER_VERIFICATION.json`.
- **Four actual CI runtime images report zero known vulnerabilities**, with OS
  and Python package coverage checked and no finding suppression. Fixed OS
  packages and removed unused pip/gosu resolve the previous image findings.
  See `docs/CONTAINER_IMAGE_AUDIT.json` and `docs/IMAGE_SECURITY_REVIEW.md`.
- Docker Engine 29.1.3, Compose 2.40.3 and Buildx 0.30.1 are installed through
  normal administrator authentication. The native stack remains running.
- Complete Python/npm dependency audits, Ruff, TypeScript/build, Actionlint and
  repository candidate Gitleaks checks pass. Private/generated files stay ignored.
- Real authenticated GitHub log download through the adapter passes; the credential
  stayed in memory. This probe did not persist an archive; fixture integration
  tests separately verify storage, expiry, snapshot authorization and downloads.
- Native Nginx/HTTPS and real loopback SMTP/STARTTLS checks passed earlier;
  they do not prove public TLS issuance or external inbox delivery.

| Phase | Implemented and verified evidence | Boundary |
|---|---|---|
| 0 — investigation | Empty baseline, real upstream CodeGraph evaluation, documented architecture | Upstream runtime was not adopted |
| 1 — infrastructure | React/FastAPI/PostgreSQL/FalkorDB, durable worker, migrations/readiness; actual Docker and native persistence/recovery/restore | Public hosting deferred |
| 2 — authentication | Argon2id, expiring hashed sessions, signup/login/logout/revocation/disable, CSRF/origins, RBAC, audited admin bootstrap, reset tokens and real local SMTP | External SMTP inbox and public HTTPS remain |
| 3 — frontend | Named route families, real API data, responsive light/dark UI, graph/source/context/history/impact/settings/admin; three browser journeys | Visual review scope and captures are recorded in UI_REVIEW.md |
| 4 — ingestion | Real public GitHub, allowed local committed Git and bounded ZIP; safe Python AST, nested ignores, resource/protocol/path limits; actual container HTTPS Git fetch | Python semantics only; other UTF-8 files get file references |
| 5 — schema | Typed nodes/edges, UUID/branch isolation, immutable graph/source snapshots, real indexes and bounded parameterized reads | Decision/fix edges require reliable evidence |
| 6 — history/CI | Real metadata sync, cursor/rate-limit/dedup/detail pagination; authenticated real log download; archive/redaction/expiry/access fixtures | GitHub PR ceilings and provider coverage gaps are disclosed |
| 7 — retrieval | Scoped symbol/neighbor/path/impact/history/context APIs, exact source and citations, nine deterministic tasks and actual query accounting | Static evidence does not prove runtime behavior |
| 8 — optional AI | Genuine graph-only results; optional provider boundary, citation validation and honest fallback tested | No real model supplied or required for selected graph-only mode |
| 9 — incremental | Hash/diff/no-change/rename/delete tests, durable leases/locks/fencing, interruption/crash recovery, publication cleanup | No distributed transaction is claimed |
| 10 — administration | Account/role/membership/ownership, jobs/retry/cancel, audit, durable log settings, worker heartbeats and measured counts/latencies/storage | Metrics cover the current API process; multi-instance export is outside scope |
| 11 — testing | 111 tests, three browser journeys, all six remote CI jobs, local Docker drill and image/dependency/secret audits | Performance observations are baselines, not SLAs |
| 12 — deployment | Optimized pinned images, non-root databases, verified graph persistence/memory flags, private DB network, CSP/headers/CORS, production config, migrations and verified backup/restore | Hosting/domain/public HTTPS and external mail setup are deferred |

## Remaining external setup

1. The user will choose hosting/domain/TLS configuration; then run public deployment checks.
2. Configure an SMTP service and designated inbox; then verify external email delivery.
3. Set deployment-specific backend credentials for continuous authenticated integrations.
4. Configure/evaluate a real model only if the user later changes graph-only mode.

No Git/Docker/container/image-audit prerequisite remains outstanding at this scope.
The normal native application retains no generated verification accounts/repositories.
Historical failed/limited scans and older test counts remain clearly dated in the
reports; they were never counted as successful checks.

The user requested Devin's exact `swe-2-max` subagents. The read-only documentation
review completed and informed status corrections. A separate container review
reached its 240-second deadline without a final result and is not counted as a
passing review; parent code review and actual local/remote checks are the evidence.
