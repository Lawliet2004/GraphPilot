# Cloud backup and recovery

The current Codespaces deployment has passed a full service restart, off-host
backup and isolated restore. The restored set matched all 20 PostgreSQL tables,
5 graph node/edge counts and SHA-256 hashes for 431 source/artifact files. Normal
and administrator login, repository access boundaries, exact source evidence and
the encrypted GitHub connection worked after restart. This verifies the current
Codespaces stack; Azure migration and VM reboot remain unverified.
See [operations evidence](CLOUD_OPERATIONS_VERIFICATION.json).

## Run a protected backup

Run from the deployed checkout with Python 3, Docker Engine and Compose v2 access:

```bash
python3 scripts/cloud_backup.py --project graphpilot-cloud-demo --restore-drill
python3 scripts/cloud_demo.py check
```

Omit `--restore-drill` for backup only. The command refuses active jobs and requires
all five source services to be running. It briefly stops web/API/worker ingress,
checks again for jobs, fingerprints the data, dumps PostgreSQL, saves FalkorDB,
and stops both databases before archiving the graph and artifact volumes. A
`finally` block attempts to restart every stopped source service, including when
a backup operation fails. Inspect readiness after any error; a Docker failure
can still require operator intervention.

The output names a new private `.data/backups/cloud-*` directory. It contains:

- A PostgreSQL custom-format dump, graph archive and artifact/source archive.
- The original private runtime environment, including the durable encryption key.
- Table row hashes, graph counts, artifact hashes, source commit and image IDs.
- A six-payload SHA-256 manifest and a separate operation report.

Directories are mode 700 and files are explicitly set to 600. Backups contain
password hashes, sessions, private source, GitHub credentials and possibly saved
model credentials. Keep the entire bundle private. Removing a model credential
from the live application does not erase older backups. Preserve
`GP_CREDENTIAL_KEY`: restoring encrypted records with a different key makes them
unusable. The final verified backup after the free-model test had zero saved
model credentials.

## Copy off-host and check it

The final backup was copied from Codespaces to the operator workstation and all
six manifest hashes were verified there. A backup on the same host is insufficient
if the host or its volumes are lost. Keep another protected copy on durable
storage that the account holder controls. No paid storage was provisioned.

For the current host, replace `BACKUP_ID` with the directory printed by the
command, using the authenticated GitHub CLI. Do not put private files in Git:

```bash
umask 077
mkdir -p .data/cloud-demo/offhost-backups
chmod 700 .data/cloud-demo/offhost-backups
gh codespace ssh -c graphpilot-demo-4jq4pvw4j7w9374gp -- \
  'cd /workspaces/GraphPilot && tar -czf - .data/backups/BACKUP_ID' \
  > .data/cloud-demo/offhost-backups/BACKUP_ID.tar.gz
chmod 600 .data/cloud-demo/offhost-backups/BACKUP_ID.tar.gz
```

Extract your trusted archive into a private directory. Preserve directory/file
permissions. Verify the saved bundle without starting Docker:

```bash
python3 - <<'PY'
from pathlib import Path
from scripts.cloud_backup import backup_metadata, load_backup
saved = load_backup(Path('.data/backups/BACKUP_ID'))
backup_metadata(saved)
print('Six payload checksums, archive paths and image metadata verified')
PY
```

## Restore a saved bundle safely

The command can exercise an existing bundle without stopping the live stack:

```bash
python3 scripts/cloud_backup.py --restore-backup .data/backups/BACKUP_ID
```

It checks owner-only permissions, expected manifest members, hashes, image IDs
and tar member paths/types. The required image IDs must already exist on that
Docker host. Keep matching images available privately; the bundle does not
include Docker images. On a replacement host, load protected saved images or
build the recorded application commit and validate the resulting deployment
separately before trusting it. An image rebuilt later need not have the same ID.

Each restore uses a new `graphpilot-restore-*` Compose project with fresh owned
volumes, an internal network, no published ports and no worker. Firebase,
GitHub and model-provider configuration is disabled in the target. It imports the
saved files, waits for PostgreSQL's final server, compares the complete saved
fingerprint and checks the isolated API's readiness. It removes only that new
target and its volumes. A project/volume collision aborts before cleanup can own
the existing target. If cleanup fails, its private config and report remain for
manual inspection; never run a broad Docker prune to resolve it.

This command is a disposable restore rehearsal. It never replaces production
volumes or promotes a restored stack. For disaster recovery, keep the original
host intact where possible, restore to a separate host, recover the same private
runtime environment and encryption key, and verify users, roles, source,
indexing, GitHub and MCP before changing the Vercel API destination. Use the
[Azure runbook](AZURE_HOSTING.md) once the student subscription is verified.

## Boot and ongoing operation

The cloud Compose services use `restart: unless-stopped`. Docker must start at
boot on a permanent host. A manually stopped service stays stopped until it is
started; inspect all five services after maintenance. Current readiness covers
PostgreSQL and FalkorDB, so also check worker observations and a real indexing
job after a host migration.

Use [availability monitoring](AVAILABILITY_MONITORING.md), watch disk capacity,
backup age, Docker health and Azure credit/expiry, and rehearse restore after
material schema/runtime changes. No backup schedule or probe is used to keep a
Codespace awake. Static frontend monitoring is enabled now; backend monitoring
and a VM reboot check belong to the final always-awake host.
