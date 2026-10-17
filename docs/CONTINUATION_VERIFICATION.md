# GraphPilot continuation verification — October 17, 2026

The repository is published on `main` at https://github.com/Lawliet2004/GraphPilot.
All commits use the user's `Lawliet2004` author/committer identity with no co-authors.
Docker Engine/Compose/Buildx installation and the remaining independently testable
container, image and remote CI work are complete. Hosting/domain setup is deferred.

| Executed check | Result |
|---|---|
| Remote CI | All six jobs pass; see `CI_VERIFICATION.json` |
| Backend/release tests | 111 pass; one upstream TestClient deprecation warning |
| Browser | Three actual-service journeys pass |
| Container runtime | Actual local and CI builds/startup/private networking/non-root PostgreSQL and graph/indexing/recreation/backup+restore pass |
| Runtime image audit | Four actual CI images, zero known vulnerabilities across reported severities, no suppressions |
| Dependencies/secrets | Complete Python and npm lock audits plus candidate Gitleaks pass |
| Static checks | Ruff, TypeScript/build and Actionlint pass |
| Git source in container | Actual safe adapter fetch of this public repository over HTTPS passes |
| External GitHub log | Real authenticated adapter download and in-memory redaction pass |
| SMTP | Actual loopback authenticated STARTTLS delivery and five failure cases pass; external inbox is unverified |
| HTTPS | Native production API/worker and built frontend behind real local Nginx/TLS pass; public HTTPS is unverified |

Evidence is in `CONTAINER_VERIFICATION.json`, `CONTAINER_LOCAL_VERIFICATION.json`,
`CONTAINER_IMAGE_AUDIT.json`, `CONTAINER_GIT_VERIFICATION.json`,
`GRAPH_CONTAINER_PERSISTENCE.json`, `GITHUB_LOG_VERIFICATION.json`,
`GATEWAY_VERIFICATION.json`, `SMTP_VERIFICATION.json` and `REPOSITORY_VERIFICATION.json`.

## Implemented corrections

SMTP uses certificate/hostname verification. Production validates exact HTTPS
origins/public URL, Secure cookies and credential-safe startup errors; API docs and
schema are disabled. Nginx refreshes Docker DNS, replaces supplied forwarding
addresses and enforces CSP/body limits. Private/generated files are excluded from
Git and build contexts. CI requires readiness and retains sanitized audit reports.
Missing/incomplete image evidence, suppressed findings and unsupported package
coverage fail the gate; all services must be represented by immutable image IDs.

Current runtime definitions retain Python 3.12, PostgreSQL 18.6 and graph engine
4.22.1 while using smaller Alpine runtimes. Unused global pip/gosu were removed;
fixed zlib/nghttp2 packages are required. Explicit non-root graph startup honors
its mounted data directory, AOF and memory policy, verified against the live process.
The first remote trial failed; later actual local/CI restore and image gates pass.
See `IMAGE_SECURITY_REVIEW.md` for current and historical scan scope.

The user requested Devin subagents using exact `swe-2-max`. Separate read-only
container and documentation reviews were launched with normal permission/trust
checks. The documentation review completed and its stale-status corrections were
checked against actual reports before applying them. No coding-agent identity was
added to Git authorship. The container review reached its 240-second deadline
without a final result; it is not counted as a passing review. Parent code review
and actual local/remote tests support the completed container checks.

## Remaining external setup

- Hosting/domain/TLS destination, explicitly deferred by the user, then public HTTPS checks.
- SMTP service and designated inbox, then external email delivery verification.
- Deployment-specific backend credentials for continuous authenticated integrations.
- A real model only if the user later changes the selected graph-only mode.

No token, signed log URL, raw provider log or private backup is included in these
reports. The log credential was held only in memory. Its probe downloaded/redacted
text without persisting an artifact; fixture tests separately cover storage,
expiry, snapshot authorization and browser downloads. Historical limited/timed-out
scans were never passes. The native app remains running and the original
requirements file is unchanged.
