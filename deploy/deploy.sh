#!/usr/bin/env bash
# =============================================================================
# Yanki prod deploy (ams-pulse pattern):
#   check env -> build -> tag by git SHA -> compose up -> /healthz -> record
#   last-good SHA, auto-rollback on failure.
#
#   Migrations run as a ONE-SHOT step here, before any container is replaced
#   (issue #16). The api container no longer migrates on boot — two
#   un-locked migrations against one DB would race on first deploy.
#
#   First exercised for real 2026-07-10 (P4.2): build -> up -> migrate ->
#   healthy -> last-good recorded, on the shared VPS, co-tenants undisturbed.
# =============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

COMPOSE="docker compose -p yanki-prod -f docker-compose.prod.yml"

# 1. Refuse to run without real secrets (never auto-create them).
if [ ! -f "$HERE/.env" ]; then
  echo "ERROR: $HERE/.env is missing." >&2
  echo "       cp deploy/.env.example deploy/.env and fill in real secrets first." >&2
  echo "       make deploy never auto-creates secrets." >&2
  exit 1
fi

# 1b. Fail fast if this is a live (DRY_RUN=0) deploy with missing LLM keys —
#     /healthz never calls a provider, so without this the deploy reports OK and
#     then every real job fails at runtime.
echo ">> checking deploy/.env"
python3 "$HERE/../scripts/check_env.py" "$HERE/.env"

# 2. Tag everything by the current git SHA.
GIT_SHA="$(git rev-parse --short HEAD)"
export GIT_SHA
echo ">> deploying yanki @ ${GIT_SHA}"

echo ">> building images (yanki-api:${GIT_SHA}, yanki-web:${GIT_SHA})"
$COMPOSE build

# Migrate BEFORE replacing any container (issue #16). The api no longer migrates
# on boot: fusing the two meant a successful migration left the previous image
# unable to start, because its alembic cannot resolve a revision it has never
# heard of — so a healthy-looking release could not be rolled back. Running it
# here also means a BAD migration costs nothing: the old stack is still serving.
echo ">> migrating schema (one-shot: alembic upgrade head)"
$COMPOSE up -d --wait db
if ! $COMPOSE run --rm --no-deps api alembic upgrade head; then
  echo "ERROR: migration failed — nothing deployed, previous release still serving" >&2
  exit 1
fi

echo ">> starting stack (containers serve; they no longer migrate)"
$COMPOSE up -d

# 3. Health-check loop against the api's loopback bind. The host port is
#    parameterized — 8140 is taken by another tenant on this VPS and 8141 is
#    the dev stack's api default on the same box, hence prod's 8142/8143 —
#    and must match the compose default; the host nginx edge proxies to this
#    same loopback bind. Migrations already ran above, so /healthz answers
#    finishes `alembic upgrade head`, so this waits out migrations too.
API_PORT="$(grep -E '^YANKI_PROD_API_PORT=' "$HERE/.env" | tail -1 | cut -d= -f2 | tr -d '[:space:]\r' || true)"
API_PORT="${API_PORT:-8143}"
echo ">> health check: http://127.0.0.1:${API_PORT}/healthz"
healthy=0
for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${API_PORT}/healthz" >/dev/null 2>&1; then healthy=1; break; fi
  sleep 2
done

# 4. Record last-good on success; auto-rollback on failure.
if [ "$healthy" -eq 1 ]; then
  echo "${GIT_SHA}" > "$HERE/.last-good"
  echo ">> deploy OK — recorded last-good = ${GIT_SHA}"
else
  echo "ERROR: health check failed — rolling back to last-good" >&2
  "$HERE/rollback.sh" || echo "ERROR: rollback also failed — inspect the server" >&2
  exit 1
fi
