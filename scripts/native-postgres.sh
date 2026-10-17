#!/usr/bin/env bash
# Development only. Uses Ubuntu packages extracted under .tools; no root services.
set -euo pipefail
cd "$(dirname "$0")/.."
project_dir="$PWD"
export LD_LIBRARY_PATH="$project_dir/.tools/postgres/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
pg_bin="$project_dir/.tools/postgres/usr/lib/postgresql/18/bin"
mkdir -p .data/postgres .data/run
chmod 700 .data .data/postgres .data/run
if [ ! -f .data/postgres/PG_VERSION ]; then
  python3 -c 'import secrets,pathlib; p=pathlib.Path(".data/postgres-password"); p.write_text(secrets.token_urlsafe(32)); p.chmod(0o600)'
  "$pg_bin/initdb" -D .data/postgres -U graphpilot -A scram-sha-256 --pwfile=.data/postgres-password > .data/initdb.log
fi
if ! "$pg_bin/pg_ctl" -D .data/postgres status > /dev/null 2>&1; then
  "$pg_bin/pg_ctl" -D .data/postgres -l "$project_dir/.data/postgres.log" -o "-p 55432 -h 127.0.0.1 -k $project_dir/.data/run -c max_connections=40 -c shared_buffers=64MB" start
fi
export PGPASSWORD="$(cat .data/postgres-password)"
if ! "$pg_bin/psql" -h 127.0.0.1 -p 55432 -U graphpilot -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='graphpilot'" | rg -q 1; then
  "$pg_bin/createdb" -h 127.0.0.1 -p 55432 -U graphpilot graphpilot
fi
python3 - <<'PY'
from pathlib import Path
password = Path('.data/postgres-password').read_text().strip()
p = Path('.env')
if not p.exists():
    p.write_text(f'GP_DATABASE_URL=postgresql+psycopg://graphpilot:{password}@127.0.0.1:55432/graphpilot\nGP_ENVIRONMENT=development\n')
    p.chmod(0o600)
PY
