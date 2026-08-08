#!/usr/bin/env bash
# =============================================================================
# Yanki prod rollback: redeploy the last-good SHA recorded by deploy.sh.
#
#   First exercised 2026-07-10 (P4.2): same-SHA rollback path ran clean and
#   healthy. The pruned-image branch (git checkout + rebuild) is still unproven.
# =============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

COMPOSE="docker compose -p yanki-prod -f docker-compose.prod.yml"

# The commit that split migrate-on-boot OUT of the prod compose (issue #16):
#   56c1fac  "fix: migrate before serving, so a rollback can actually roll back"
#            (2026-08-03)
# Before it, api booted as `sh -c "alembic upgrade head && uvicorn ..."`, fusing a
# schema change to the container swap. Rebuilding a pre-56c1fac tree during a
# rollback re-arms that: the older image looks for a revision the live DB is now
# stamped at, cannot resolve it, alembic exits 255, the `&&` never starts uvicorn,
# and `restart: unless-stopped` turns it into a crash loop — at the moment of
# maximum stress. So we REFUSE to rebuild any tree at/behind that boundary.
# Re-derive the boundary at any time with:
#   git log --oneline -S 'sh -c "alembic upgrade head' -- deploy/docker-compose.prod.yml
# (the older of the two hits is the scaffold that introduced the fused command;
#  the newer is the split that removed it — this SHA).
MIGRATE_ON_BOOT_SPLIT="56c1fac029986f2f596a9c54aebf8097ea343851"

if [ ! -f "$HERE/.last-good" ]; then
  echo "ERROR: no $HERE/.last-good — there is no known-good release to roll back to." >&2
  exit 1
fi

GIT_SHA="$(cat "$HERE/.last-good")"
export GIT_SHA
echo ">> rolling back to ${GIT_SHA}"

# Where the working tree sits right now. A pruned-image rebuild has to check out
# the last-good SHA, and we must put the tree back here afterwards so the NEXT
# deploy runs from a known branch instead of a surprising detached HEAD.
ORIG_REF="$(git symbolic-ref --quiet --short HEAD || git rev-parse HEAD)"

# The last-good images should already be built locally from the prior deploy.
# If they were pruned, rebuild — but check out the last-good SHA first, so we
# rebuild the KNOWN-GOOD code, not whatever broken tree triggered this rollback.
if [ -z "$(docker images -q "yanki-api:${GIT_SHA}")" ]; then
  echo ">> yanki-api:${GIT_SHA} not found locally — must check it out and rebuild"

  # Refuse to rebuild a tree that predates the migrate-on-boot split: it would
  # migrate-on-boot into a crash loop during the rollback (see above). Fail loud
  # with an actionable next step rather than try to be clever and recover.
  # `--is-ancestor SPLIT SHA` is 0 when SHA is the split or a descendant (safe,
  # serves-only), non-zero when SHA is behind it OR cannot be verified against it
  # (unknown commit) — both of which we treat as "do not rebuild".
  if ! git merge-base --is-ancestor "$MIGRATE_ON_BOOT_SPLIT" "$GIT_SHA" 2>/dev/null; then
    echo "ERROR: last-good ${GIT_SHA} is at/behind the migrate-on-boot split ${MIGRATE_ON_BOOT_SPLIT}" >&2
    echo "       (or cannot be verified as a descendant of it). Rebuilding that tree would fuse" >&2
    echo "       'alembic upgrade head' into the api boot command and crash-loop the stack against" >&2
    echo "       the current schema. Refusing to rebuild." >&2
    echo "       Recover by hand: roll back to a last-good SHA at or after ${MIGRATE_ON_BOOT_SPLIT}," >&2
    echo "       or build the images from ${GIT_SHA} with a serves-only compose command" >&2
    echo "       (git checkout ${MIGRATE_ON_BOOT_SPLIT} -- deploy/docker-compose.prod.yml first)." >&2
    echo "       See deploy/AUTODEPLOY.md." >&2
    exit 1
  fi

  # From here we mutate the working tree. Guarantee we return to ORIG_REF on ANY
  # exit (success, a failed health check, or a set -e abort) — never leave prod
  # in detached HEAD.
  trap 'git checkout --quiet "$ORIG_REF" 2>/dev/null \
        || echo "WARNING: could not restore checkout to ${ORIG_REF}; run: git checkout ${ORIG_REF}" >&2' EXIT

  git checkout --quiet "${GIT_SHA}"
  $COMPOSE build
fi

$COMPOSE up -d

# Verify the rollback actually came up, so a failed rollback exits non-zero
# instead of falsely printing "complete". Port must match deploy.sh / the
# compose loopback bind (YANKI_PROD_API_PORT, default 8143).
API_PORT="$(grep -E '^YANKI_PROD_API_PORT=' "$HERE/.env" 2>/dev/null | tail -1 | cut -d= -f2 | tr -d '[:space:]\r' || true)"
API_PORT="${API_PORT:-8143}"
echo ">> health check: http://127.0.0.1:${API_PORT}/healthz"
healthy=0
for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${API_PORT}/healthz" >/dev/null 2>&1; then healthy=1; break; fi
  sleep 2
done

if [ "$healthy" -eq 1 ]; then
  echo ">> rollback to ${GIT_SHA} complete and healthy"
else
  echo "ERROR: rollback to ${GIT_SHA} failed its health check — inspect the server" >&2
  exit 1
fi
