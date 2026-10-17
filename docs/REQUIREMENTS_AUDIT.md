# Original requirements audit — October 16, 2026

The original attachment and `REQUIREMENTS.md` have identical SHA-256:
`74852d1e4c9d338a76d93d19569e1cf66082fe064ce2f75cef0a556686314cc0`.
This audit distinguishes the verified native demonstration from container and
external-service checks. It does not certify production security.

| Requested scope | Implemented and executed evidence | Boundary / remaining verification |
|---|---|---|
| Investigation and reuse | Empty directory baseline, actual upstream CodeGraph checkout and architectural evaluation in ARCHITECTURE.md | Upstream runtime not adopted; safe Python AST adapter is a documented choice |
| React/FastAPI/PostgreSQL/FalkorDB stack | Running native services, migrations 0001–0007, durable external worker, HTTP readiness, lockfiles, Compose and optimized image definitions | Docker image build, network, restart and volume restore have not run |
| Authentication and permissions | Argon2id, hashed session tokens, expiry/logout/revocation/disable, CSRF/origins, RBAC/membership on graph/evidence/artifacts/context, reset-token fixture, audited admin bootstrap | Real authenticated loopback SMTP/STARTTLS and native Nginx/TLS checks pass; external inbox delivery and public HTTPS deployment remain unverified |
| Frontend page families | Landing, signup/login/reset, workspace/recent data, connect, graph, overview, context/history, impact/diagnostics, settings/activity/admin; light/dark, keyboard node list and mobile source focus | Desktop/mobile browser captures and tablet/error checks; independent finish review certifies only its six requested fixes |
| Ingestion adapters and security | Actual public clone, allowed local committed Git, ZIP; nested ignores, binary/dependency exclusions, no code execution, traversal/symlink/protocol checks, streamed request/parser/graph bounds | Python semantics guaranteed; other UTF-8 files have file references. Private GitHub/Git LFS/submodules and dynamic runtime resolution are not promised |
| Typed schema/isolation | Stable UUID/branch IDs, typed entity/relationship allowlists, real indexes, bounded parameterized reads, immutable branch/snapshot/source navigation, integrity checks | Decision/fix/supersession edges are absent when reliable evidence is absent; no inferred issue fixes |
| GitHub/CI | Actual Hello-World sync: 25 requests, 177 published entities; recorded rate limits/dedup/resume, PR and commit detail pagination, safe log redirect/storage/redaction/expiry, exact matching-commit pytest links | Logs can be unavailable; successful external log download is unverified (live unauthenticated probe returned 403). API PR ceilings: 250 commits, 3000 files; pending pages and uncertainty are disclosed |
| Deterministic retrieval | Symbol/neighbor/path/impact/history/context APIs, identifier/issue/PR/SHA/CI interpretation, transparent rank, bounded two-hop retrieval/source citations; nine fixed tasks with exact graph-query counts in RETRIEVAL_BENCHMARK.json | No semantic/vector search needed; static paths do not establish runtime behavior |
| Optional AI | Graph-only mode, bounded evidence and optional OpenAI-compatible synthesis, citation-ID validation, failure fallback, explicit untrusted-data/system boundary, no tools/shell/Cypher | User explicitly chose graph-only because no model is available. Successful model inference and model-behavior injection evaluation are not claimed |
| Incremental/durable work | Content/parser hashes, semantic graph diffs, no-change zero writes, rename/delete/interruption retry, lease/advisory locks, killed-worker recovery and stale fencing; lost-commit acknowledgement preserves published graph/source | An uncertain SQL/graph cleanup defers safely; owned repository removal can clean leftovers. No distributed transaction or hard disk quota is claimed |
| Admin/monitoring | User/role/disable, audited access/ownership choices, jobs/retry/cancel, durable allowlisted log settings, readiness/worker heartbeats, counts/errors/query timings/storage | Timings are bounded per API process; multi-instance monitoring export is outside this local demonstration |
| Lifecycle/recovery | Owner-confirmed durable removal, snapshot retirement preserving heads/conversation pins/shared trees, expired logs, crash fault tests; native persistence, DB-outage recovery and isolated backup/restore verified | Audit/retirement metadata remain; pins can extend retention. Container-volume restore still needs Docker |
| Tests/performance | Ruff, TypeScript/production build, 81 real-database backend tests; three browser journeys; live source and metadata verification; 20 sessions/200 correct searches; 400-file/4000-function real index | Warm host measurements are baselines, not SLAs or maximum-capacity tests. Remote Actions have not run (no Git remote configured) |
| Deployment/documentation | Environment example without credentials, private DB networks, Secure-cookie profile, gateway CSP, health/restart definitions, install/run/admin/provider/backup/troubleshooting instructions | Native Nginx/TLS deployment checks pass; container runtime, public HTTPS target and container-image vulnerability checks remain unverified |

## Environment gate

There is no Docker/Podman/nerdctl/Buildah executable or running Docker socket on
this host. User/mount/network namespaces are available, but `newuidmap` and
`newgidmap`, required for rootless Docker's subordinate UID mappings, are absent.
`sudo -n true` reports that interactive authentication is required. Installing
those privileged helpers or supplying a Docker runtime requires an external
host change; no system security policy was changed to bypass it. Compose config
validation passes with non-secret validation inputs. Native substitutes are
reported separately and do not count as executed container tests.

## Verification artifacts

- LIVE_VERIFICATION.json — actual itsdangerous source/search/context/logout.
- HISTORY_VERIFICATION.json — actual GitHub metadata sync and durable probe removal.
- RETRIEVAL_BENCHMARK.json — nine known tasks, query counts/latency/context bytes.
- PERFORMANCE.json — 20 authenticated sessions, 200 correct HTTP searches.
- CAPACITY_VERIFICATION.json — real 400-file index, source proof, bounded graph load,
  worker CPU/RSS samples and owned-data removal.
- PERSISTENCE_VERIFICATION.json, WORKER_RECOVERY.json, RESTORE_VERIFICATION.json —
  actual native persistence/outage/isolated restore observations.
- DEPENDENCY_AUDIT.json and TEST_REPORT.md — audits, failures/fixes, executed checks.

The functional native demo is reviewable. The full container/production verification
gates remain open; successful external SMTP, external log and model-provider results have
not been invented.


## New-chat continuation

The user confirmed no Git remote or HTTPS deployment target is available. The
host runtime gate was rechecked and remains open. Native Nginx/TLS and real local
SMTP protocol checks are now executed separately from that gate, with certificate
verification and secure failure handling. Current backend suite: 81 passed; current
browser regression: three passed in 49.6 s. Production public-URL validation and
API documentation cleanup have regression checks.

New reports: `GATEWAY_VERIFICATION.json`, `SMTP_VERIFICATION.json`,
`CONTAINER_VERIFICATION.json`, `IMAGE_METADATA_VERIFICATION.json`,
`REPOSITORY_VERIFICATION.json` and `CONTINUATION_VERIFICATION.md`.
The guarded container harness and CI image audit are prepared; their runtime
branches have not executed. Actionlint and candidate-only secret scanning pass.
No model was configured, and no external SMTP/log success was substituted.

## October 17 image follow-through

Daemonless scans of the selected upstream images completed and exposed real
package findings; the Python and FalkorDB bases retain high findings. The current
PostgreSQL candidate uses Alpine 18.6 with a non-root derivative that removes the
unused Go helper; actual build/start/restore and merged-image audit are unexecuted.
Publisher inventories are cryptographically bound to the selected image digests;
missing OS identification and explicit declared-OS analysis are recorded separately.
An isolated 40-package production-only native import passes. Image-related work is
documented in `IMAGE_SECURITY_REVIEW.md`; residual findings remain an open release
gate alongside the missing runtime and deployment destination.
