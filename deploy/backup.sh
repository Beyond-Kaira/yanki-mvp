#!/usr/bin/env bash
# =============================================================================
# Yanki — take ONE verified dump of the production database.
#
#   The `yanki_pgdata` volume is the only copy of every analysis, user, session,
#   organization, audit event and billing row. `rollback.sh` restores the
#   *image*; it has never been able to restore a row. This is the other half.
#
#   Three properties, and the third is the one that makes the first two worth
#   anything:
#
#   1. **Custom format** (`--format=custom`), not plain SQL — it is compressed,
#      and `pg_restore` can list its contents, which is what lets a dump be
#      checked rather than assumed.
#   2. **Verified before it is kept.** A truncated or empty dump is worse than
#      no dump, because it is a backup you believe in. The file is written to a
#      `.partial` name, its table-of-contents is parsed, its size floor is
#      checked, and only then is it renamed into place. A dump that fails any of
#      that is deleted and the script exits non-zero.
#   3. **On this box only.** An off-box copy needs a destination and credentials
#      that are the operator's to choose (operator item B13); this script
#      deliberately does not invent one. A dump beside the database it came from
#      survives a bad migration and a dropped table — the failures that actually
#      happen here — and does not survive losing the VPS. Say so plainly rather
#      than implying more protection than exists: see deploy/BACKUP.md.
#
# Usage:
#   deploy/backup.sh                     # timestamped dump + prune
#   deploy/backup.sh --label pre-0019    # name it after why you took it
#   deploy/backup.sh --quiet             # only errors (for cron)
#
# Environment (all optional):
#   YANKI_BACKUP_DIR      where dumps live         (default ~/yanki-backups)
#   YANKI_BACKUP_KEEP     how many to keep         (default 14)
#   YANKI_BACKUP_MIN_KB   size floor for a dump    (default 32)
# =============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

COMPOSE="docker compose -p yanki-prod -f docker-compose.prod.yml"
BACKUP_DIR="${YANKI_BACKUP_DIR:-$HOME/yanki-backups}"
KEEP="${YANKI_BACKUP_KEEP:-14}"
MIN_KB="${YANKI_BACKUP_MIN_KB:-32}"
LABEL=""
QUIET=0

while [ $# -gt 0 ]; do
  case "$1" in
    --label) LABEL="$2"; shift 2 ;;
    --quiet) QUIET=1; shift ;;
    -h|--help) sed -n '2,45p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

say() { [ "$QUIET" -eq 1 ] || echo "$@"; }

if [ ! -f "$HERE/.env" ]; then
  echo "ERROR: $HERE/.env is missing — this script only backs up the prod stack." >&2
  exit 1
fi

# The db service must be up. Starting it here would be the wrong favour: if the
# stack is down, that is a fact the operator should learn from this script's
# failure rather than have it quietly paper over.
if ! $COMPOSE ps --status running --services 2>/dev/null | grep -qx db; then
  echo "ERROR: the yanki-prod db service is not running — nothing to back up." >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

# A dump is the whole database in one file: password hashes, email addresses,
# audit payloads. 0700/0600 is not decoration.
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
NAME="yanki-${STAMP}${LABEL:+-${LABEL}}.dump"
TARGET="$BACKUP_DIR/$NAME"
PARTIAL="$TARGET.partial"

# Refuse rather than fill the disk. This VPS is shared with four other
# production tenants and its free space swings; a backup that triggers a
# disk-full incident has cost more than it saved.
FREE_MB="$(df -Pm "$BACKUP_DIR" | awk 'NR==2 {print $4}')"
if [ "${FREE_MB:-0}" -lt 512 ]; then
  echo "ERROR: only ${FREE_MB}MB free at ${BACKUP_DIR} — refusing to dump." >&2
  echo "       Prune old dumps or free space first (df -h)." >&2
  exit 1
fi

say ">> dumping yanki-prod db → ${TARGET}"
umask 077
if ! $COMPOSE exec -T db pg_dump -U yanki -d yanki --format=custom --no-owner > "$PARTIAL"; then
  rm -f "$PARTIAL"
  echo "ERROR: pg_dump failed — no dump written." >&2
  exit 1
fi

# --- Verify before keeping ---------------------------------------------------
SIZE_KB="$(du -k "$PARTIAL" | cut -f1)"
if [ "$SIZE_KB" -lt "$MIN_KB" ]; then
  rm -f "$PARTIAL"
  echo "ERROR: dump is ${SIZE_KB}KB, under the ${MIN_KB}KB floor — treating as empty." >&2
  exit 1
fi

# Read the WHOLE archive back, decompressing every entry and throwing the SQL
# away. `pg_restore --file=/dev/null` is the cheap way to do that: 1.1s on a
# 2.7 MB dump here.
#
# The obvious check — `pg_restore --list` — was written first and thrown away,
# because it is exactly the kind of check that reassures without protecting. A
# custom archive keeps its table of contents in the **header**, so a dump
# truncated to its first 100 KB still lists all 207 entries and passes. Measured,
# not assumed. It catches a corrupt header and nothing else, and a backup check
# that passes a half-written file is worse than no check, because it is the
# reason nobody looks again.
#
# Both run in a short-lived postgres:16 container with the backup directory
# bind-mounted **read-only**. Piping the dump in on stdin does not work at all
# (reading a custom archive needs to seek, so a perfect dump fails), and the
# other way to give it a path — copying it into the running production db
# container — means writing a full copy of the database into a production
# container in order to run a safety check.
if ! docker run --rm -v "$BACKUP_DIR":/backups:ro postgres:16 \
      pg_restore --file=/dev/null "/backups/$(basename "$PARTIAL")" >/dev/null 2>&1; then
  rm -f "$PARTIAL"
  echo "ERROR: the dump could not be read back in full — truncated or corrupt." >&2
  exit 1
fi

mv "$PARTIAL" "$TARGET"
chmod 600 "$TARGET"
say ">> ok: $(du -h "$TARGET" | cut -f1), read back in full"

# --- Prune -------------------------------------------------------------------
# Newest KEEP survive. Deliberately count-based rather than age-based: an age
# rule silently leaves you with nothing if the schedule stops, and "no backups"
# should require somebody to have deleted them.
mapfile -t OLD < <(ls -1t "$BACKUP_DIR"/yanki-*.dump 2>/dev/null | tail -n +$((KEEP + 1)))
if [ "${#OLD[@]}" -gt 0 ]; then
  say ">> pruning ${#OLD[@]} dump(s) beyond the newest ${KEEP}"
  rm -f "${OLD[@]}"
fi

say ">> ${BACKUP_DIR}: $(ls -1 "$BACKUP_DIR"/yanki-*.dump 2>/dev/null | wc -l) dump(s), $(du -sh "$BACKUP_DIR" | cut -f1) total"
echo "$TARGET"
