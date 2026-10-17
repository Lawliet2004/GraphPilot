# Image review — October 17, 2026 (Asia/Kolkata)

Current runtime follow-through: Docker Engine 29.1.3, Compose 2.40.3 and Buildx
0.30.1 are now installed via the normal administrator prompt. GitHub CI executed:
110 backend/release tests and three browser journeys passed; the first container
run reached backup/restore and failed in the graph-volume restore helper. That
failure is being reproduced; it is not a passing container gate.

The current candidate definitions use pinned Python 3.12 Alpine 3.24 and the
publisher's FalkorDB **server-only 4.22.1 Alpine** image. The engine version stays
4.22.1. The Python publisher inventory reports six medium/one low finding and
no high/critical findings with an explicit publisher-sourced Alpine declaration.
Actual built-image scans and complete container verification are pending. The
Trixie findings below describe the prior definitions and are retained as history.

Release-check follow-up: CI now retains sanitized per-image JSON, verifies exact
service image-ID coverage and fails for missing/incomplete scans, unrecognized
OS/package inventory, modified findings or end-of-life OS. High/critical findings
remain blocking even when no fix is listed. Local release-gate tests pass; no
container execution or new image scan occurred. Prior image findings below remain
open. See `RELEASE_GATE_VERIFICATION.json`.

These audits ran without a container daemon. They are separate from the 81 passing
application tests and Python/npm dependency audits. JSON timestamps use UTC.
GraphPilot's API/worker, web and derived PostgreSQL images remain unbuilt/unaudited.

## Executed evidence

| Published base/service | Result | Source |
|---|---|---|
| Original Nginx 1.28 Alpine | 60 high, 2 critical | REMOTE_IMAGE_AUDIT_INITIAL.json |
| Original Python Bookworm | 61 high, 2 critical | REMOTE_IMAGE_AUDIT_INITIAL.json |
| Original PostgreSQL Bookworm | 95 high, 4 critical | REMOTE_IMAGE_AUDIT_INITIAL.json |
| Replacement Nginx 1.30.6 Alpine | 1 medium; no high/critical | Complete filesystem scan |
| Replacement Python Trixie | 44 high; no critical | Complete filesystem scan |
| Evaluated PostgreSQL 18.6 Trixie | 85 high, 2 critical | Complete filesystem scan |
| FalkorDB pinned 4.22.1 | 36 high; no critical | Complete filesystem scan |

These are scanner findings, not proof of exploitability. Remaining findings were
not suppressed. The strict high/critical CI image gate remains enabled. The full
selected-image evidence is archived in `REMOTE_IMAGE_AUDIT_TRIXIE.json`, including
earlier failed attempts. Current PostgreSQL Alpine results are separate in
`POSTGRES_ALPINE_FULL_AUDIT.json` and `POSTGRES_ALPINE_INVENTORY.json`; inspect their
status before treating a scan as completed.

## Implemented changes

Nginx now uses the maintained, digest-pinned 1.30.6 Alpine image. Python/Node use
pinned Trixie variants, preserving Python 3.12 and Node 22. The Python base retains
44 high findings, requiring review/remediation before production.

The Trixie PostgreSQL alternative retains a critical libxml2 finding with no listed
fix, plus a critical Go stdlib finding in its gosu helper. The current definition
instead uses official PostgreSQL **18.6 Alpine 3.24**. A small derived Dockerfile
removes `/usr/local/bin/gosu` and starts as the existing `postgres` user, preserving
the inherited database/entrypoint. The Alpine candidate's digest-bound inventory,
with explicitly declared `alpine/3.24` from the publisher Dockerfile, reports
24 high/one critical finding, all in the bundled Go stdlib. No high/critical OS
findings were reported for that declaration. The final derived image still needs
an actual build, initialization/ownership, restart/restore and merged-image audit.
The container harness checks that PostgreSQL runs non-root and gosu is absent.

[The publisher supports non-root startup](https://hub.docker.com/_/postgres#arbitrary---user-notes),
provided data-directory ownership matches. Its [Alpine 18 Dockerfile](https://github.com/docker-library/postgres/blob/master/18/alpine3.24/Dockerfile)
creates the postgres user/volume directory and retains `/var/lib/postgresql` as
the declared volume. Existing bind mounts may need deliberate ownership preparation.
The normal native PostgreSQL instance and its data were not changed.

## Inventory limitations

Publisher SPDX attestations were SHA-256 checked from the pinned image index to
the selected linux/amd64 attestation/inventory, including matching subjects.
Initial inventories did not identify their OS to Trivy and are explicitly marked
`inventory_limited`; their empty finding lists do not establish clean OS packages.
The Alpine candidate instead records a publisher-sourced OS declaration. The tool
can also use the OS of an already completed filesystem scan at the same digest.
Neither method constitutes execution of the image or a GraphPilot-built-image audit.
FalkorDB supplied no matching inventory attestation; its complete filesystem scan
is the evidence for its 36 high findings.

The default vulnerability DB mirror timed out; the official GHCR copy downloaded.
Registry TLS errors/timeouts and a public mirror failure were recorded separately.
Longer direct scans subsequently completed. None of those failed attempts counted
as passes, and no untested major graph-engine upgrade was substituted.

## Remaining release gates

- Review/remediate Python/FalkorDB high findings and any remaining PostgreSQL findings.
- Build/run/audit the actual API/worker, web and derived PostgreSQL images.
- Verify private networking, fresh-volume permissions, restart persistence and restore.
- Execute remote CI and public HTTPS checks once destinations/runtime are supplied.

An isolated **40-package production-only native environment** imports the real
production API successfully without development dependencies; see
`PRODUCTION_IMPORT_VERIFICATION.json`. That check does not prove a container image.

Final PostgreSQL Alpine filesystem attempt: **timed out after a 930-second wall limit**. Its current result is unknown; the declared-OS inventory is a separate check. Actual derived-image build/audit and fresh-volume/non-root startup remain unexecuted. No timed-out transfer was labeled clean.
