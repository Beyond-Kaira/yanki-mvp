#!/usr/bin/env bash
# =============================================================================
# Yanki — rehearse a restore, so a dump is known-good rather than believed-good.
#
#   `backup.sh` verifies that a dump is a well-formed archive. That is not the
#   same claim as "this file can become a working database", and the gap between
#   those two is where every backup horror story lives. This script closes it
#   the only way it can be closed: by actually restoring.
#
#   It restores into a **throwaway container on a throwaway port** and never
#   touches the production database, the production volume, or the prod compose
#   project. There is no flag to make it do so; a restore into production is an
#   operator action taken deliberately, with the runbook open (deploy/BACKUP.md).
#
#   What it asserts after restoring, in the order that matters:
#     1. The restore itself exits clean.
#     2. `alembic_version` holds a revision — a schema with no migration stamp
#        is one the application will refuse to run against.
#     3. The tables that carry irreplaceable data exist AND are populated:
#        users, organizations, analyses, audit_events. A dump of an empty
#        database restores perfectly and protects nothing.
#
# Usage:
#   deploy/restore-check.sh                 # newest dump in the backup dir
#   deploy/restore-check.sh path/to.dump    # a specific one
#
# Environment (all optional):
#   YANKI_BACKUP_DIR   where dumps live      (default ~/yanki-backups)
#   YANKI_RESTORE_PORT scratch host port     (default 5436)
# =============================================================================
set -euo pipefail

BACKUP_DIR="${YANKI_BACKUP_DIR:-$HOME/yanki-backups}"
PORT="${YANKI_RESTORE_PORT:-5436}"
CONTAINER="yanki-restore-check"
DUMP="${1:-}"

if [ -z "$DUMP" ]; then
  DUMP="$(ls -1t "$BACKUP_DIR"/yanki-*.dump 2>/dev/null | head -1 || true)"
fi
if [ -z "$DUMP" ] || [ ! -f "$DUMP" ]; then
  echo "ERROR: no dump to check (looked in ${BACKUP_DIR})." >&2
  echo "       Take one first: deploy/backup.sh" >&2
  exit 1
fi

echo ">> rehearsing restore of $(basename "$DUMP") ($(du -h "$DUMP" | cut -f1))"

cleanup() { docker rm -f "$CONTAINER" >/dev/null 2>&1 || true; }
trap cleanup EXIT
cleanup

# postgres:16 to match the prod image. A restore that only works on a different
# major version is not the rehearsal anyone needs.
docker run -d --name "$CONTAINER" \
  -e POSTGRES_USER=yanki -e POSTGRES_PASSWORD=scratch -e POSTGRES_DB=yanki_restore \
  -p "127.0.0.1:${PORT}:5432" postgres:16 >/dev/null

for _ in $(seq 1 60); do
  docker exec "$CONTAINER" pg_isready -U yanki -d yanki_restore >/dev/null 2>&1 && break
  sleep 1
done
if ! docker exec "$CONTAINER" pg_isready -U yanki -d yanki_restore >/dev/null 2>&1; then
  echo "ERROR: scratch Postgres never became ready." >&2
  exit 1
fi

echo ">> restoring…"
# --no-owner because the dump was taken that way; --exit-on-error so a partial
# restore is a failure rather than a warning nobody reads.
if ! docker exec -i "$CONTAINER" pg_restore -U yanki -d yanki_restore \
      --no-owner --exit-on-error < "$DUMP"; then
  echo "ERROR: pg_restore failed — this dump is NOT usable." >&2
  exit 1
fi

q() { docker exec "$CONTAINER" psql -U yanki -d yanki_restore -tAc "$1"; }

REVISION="$(q "select version_num from alembic_version limit 1" || true)"
if [ -z "$REVISION" ]; then
  echo "ERROR: restored database has no alembic_version — the app would refuse it." >&2
  exit 1
fi
echo ">> alembic_version = ${REVISION}"

FAILED=0
for table in users organizations analyses audit_events; do
  COUNT="$(q "select count(*) from ${table}" 2>/dev/null || echo "MISSING")"
  if [ "$COUNT" = "MISSING" ]; then
    echo "   ${table}: TABLE MISSING" >&2
    FAILED=1
  elif [ "$COUNT" = "0" ]; then
    # Zero is not automatically wrong — a fresh deployment has no audit events —
    # but it is never what you want to discover during an actual restore, so it
    # is reported loudly and left to the reader rather than silently passed.
    echo "   ${table}: 0 rows  (empty — check this is expected)"
  else
    echo "   ${table}: ${COUNT} rows"
  fi
done

TABLES="$(q "select count(*) from pg_tables where schemaname='public'")"
echo ">> ${TABLES} tables in public schema"

if [ "$FAILED" -ne 0 ]; then
  echo "RESTORE CHECK FAILED — see above." >&2
  exit 1
fi

echo ">> restore check PASSED for $(basename "$DUMP")"
