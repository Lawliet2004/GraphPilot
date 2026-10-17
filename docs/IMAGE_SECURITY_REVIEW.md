# Image security review — October 17, 2026

All four actual runtime images in [CI run 39006962607](https://github.com/Lawliet2004/GraphPilot/actions/runs/39006962607)
report **zero known vulnerabilities at scan time**, across all reported severities.
The strict high/critical gate remains enabled; no image findings were suppressed.
See `CONTAINER_IMAGE_AUDIT.json` for image IDs, package coverage and source commit.

| Actual runtime family | Current definition | Findings |
|---|---|---|
| API / worker / migration | Python 3.12 Alpine 3.24, production lock only | 0 |
| Web | Nginx 1.30.6 Alpine with fixed zlib | 0 |
| PostgreSQL | Official 18.6 Alpine derivative, non-root, gosu removed | 0 |
| Graph | Publisher's server-only FalkorDB 4.22.1 Alpine, non-root | 0 |

## Changes and verification

Python remains 3.12; the graph engine remains 4.22.1. Alpine runtime images replace
the earlier Debian definitions. The API image removes unused global pip and
ensurepip after dependencies are built. Web/API/PostgreSQL require fixed zlib;
PostgreSQL also requires fixed nghttp2-libs and removes the unused Go-based gosu.
The publisher's [zlib fix](https://github.com/alpinelinux/aports/blob/3.24-stable/main/zlib/APKBUILD)
and [nghttp2 fix](https://github.com/alpinelinux/aports/blob/3.24-stable/main/nghttp2/APKBUILD)
confirm the minimum package versions. The API, Node, uv, web, database and graph
inputs are digest-pinned; OS security updates are applied while building.

The graph image contains only the server. Its explicit entrypoint honors the
configured `/data`, AOF, 768 MiB memory limit and noeviction policy. The vendor's
wrapper ignores the supplied command, so relying on it would leave those settings
unused. The verifier now checks effective configuration, non-root ownership and
private network/port isolation. PostgreSQL's non-root initialization and absent
gosu are checked too.

Actual builds, startup, worker indexing, source authorization, API recreation,
SQL/graph/artifact backup and restore, session/source persistence and owned cleanup
pass both locally and in CI. `CONTAINER_LOCAL_VERIFICATION.json`,
`CONTAINER_VERIFICATION.json` and `GRAPH_CONTAINER_PERSISTENCE.json` record the scope.
The non-root API image also imports its real runtime dependencies, verifies Argon2
and fetches this public repository over HTTPS through the actual safe Git adapter;
see `CONTAINER_GIT_VERIFICATION.json`.

The first remote trial failed in the previous graph-volume restore path. Subsequent
current-image drills passed. The failed run remains in `CI_VERIFICATION.json`;
it was never counted as a pass. Docker Engine 29.1.3, Compose 2.40.3 and Buildx
0.30.1 are installed on the development host through normal administrator authentication.

## Historical evidence

| Previous published base/service | Recorded high / critical findings |
|---|---|
| Nginx 1.28 Alpine | 60 / 2 |
| Python Bookworm | 61 / 2 |
| PostgreSQL Bookworm | 95 / 4 |
| Python Trixie | 44 / 0 |
| PostgreSQL Trixie alternative | 85 / 2 |
| Full FalkorDB 4.22.1 Debian image | 36 / 0 |

These results remain in `REMOTE_IMAGE_AUDIT_INITIAL.json` and
`REMOTE_IMAGE_AUDIT_TRIXIE.json`. The previous Alpine transfer timeout and limited
publisher inventories remain historical evidence; they are superseded for the
current runtime decision by actual built-image scans. Inventory-only checks never
proved container execution, complete filesystem coverage or an application-image pass.

## Remaining scope

Public hosting/domain/HTTPS setup is deferred by the user. External SMTP inbox
delivery is unconfigured; authenticated local SMTP/TLS checks pass. Real GitHub
job-log download now passes through the application adapter with a token held only
in memory. Graph-only mode remains selected; no application LLM is required.
