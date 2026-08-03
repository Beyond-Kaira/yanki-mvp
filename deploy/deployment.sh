#!/usr/bin/env bash
# =============================================================================
# deployment.sh — Yanki prod deploy for the HOST-nginx edge (nginx-aware variant
# of deploy/deploy.sh).
#
# WHY A SECOND SCRIPT (this is the deploy path; deploy.sh is the engine's origin)
# -------------------------------------------------------------------------------
# deploy/deploy.sh builds, `compose up`s, and health-checks the api's PRIVATE
# loopback port (127.0.0.1:8143/healthz) — it proves the CONTAINER is up, but
# not that the edge routes to it.
#
# This script keeps deploy.sh's exact docker-compose engine and its .last-good
# rollback discipline, but moves the health gate to the PUBLIC url
# (https://yanki.beyondkaira.com/healthz). That single change is what makes it
# "nginx-aware": a green run proves the whole host-nginx path-split
# (/api/* + /healthz -> api, else -> web) actually serves, end to end. The
# host-nginx edge (deploy/nginx/yanki.beyondkaira.com.conf) is live, so THIS
# is the standard deploy; deploy.sh remains for container-only health checks
# (or override HEALTH_URL, see below).
#
# deploy.sh is left UNTOUCHED. This file adds nothing to the live edge on its
# own; it is a deploy driver you run by hand.
#
# THE `set -e` BUG THIS FILE IS SHAPED AROUND (the lesson from deploy.sh)
# ----------------------------------------------------------------------
# Under `set -euo pipefail` a bare failing command exits the script, so a
# rollback written as `step; if [ $? -ne 0 ]; then rollback; fi` is DEAD CODE —
# `set -e` already exited. Every failure path here is
#   if ! <step>; then rollback; exit 1; fi
# because a command in an `if` condition is exempt from `set -e`.
#
# THE ORDER (six steps)
#   1. preflight   tools, .env, secrets sanity, clean tree
#   2. build       compose build (images tagged by git SHA)
#   3. last-good   read the SHA the box currently serves, BEFORE changing it
#   4. migrate     alembic upgrade head in a one-shot container, BEFORE any
#                  running container is replaced (issue #16). Fail -> exit,
#                  previous release untouched.
#   5. apply       compose up -d (containers serve; they no longer migrate)
#   6. health      bounded curl loop vs the PUBLIC url, asserting a real body
#                  marker ("status"/"ok"), hard-fail timeout. Fail -> rollback.
#   7. record      write .last-good = new SHA (only after it is proven healthy)
#
# CONFIG (env or deploy/.env; values never printed):
#   HEALTH_URL     public health url. Default https://yanki.beyondkaira.com/healthz
#                  Override to rehearse before cutover, e.g.
#                    HEALTH_URL='https://yanki.beyondkaira.com/healthz' \
#                    HEALTH_CURL_OPTS='--resolve yanki.beyondkaira.com:443:127.0.0.1'
#                  or point at the loopback api: http://127.0.0.1:8143/healthz
#   HEALTH_EXPECT  substring the body MUST contain. Default: ok
#   HEALTH_KEY     second substring the body MUST contain. Default: status
#   HEALTH_TRIES   curl attempts (2s apart). Default: 45  (~90s, covers migrate)
#   HEALTH_CURL_OPTS  extra curl args (e.g. --resolve ...). Default: empty
#   DEPLOY_ALLOW_DIRTY=1  skip the clean-tree guard (rehearsal only)
#
# EXIT: 0 healthy · 1 failed (rolled back where possible) · 2 bad usage
# =============================================================================
set -euo pipefail

# Resolve our own directory from BASH_SOURCE (never $PWD): this script lives in
# deploy/, next to deploy.sh / rollback.sh / docker-compose.prod.yml.
HERE="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -P "$HERE/.." && pwd)"
cd "$HERE"

CHECK_ONLY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --check | --dry-run) CHECK_ONLY=1 ;;
    -h | --help)
      sed -n '2,60p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      printf 'deployment: unknown argument %s\n' "$1" >&2
      exit 2
      ;;
  esac
  shift
done

say()  { printf '\n== %s\n' "$1"; }
info() { printf '   %s\n' "$1"; }
oops() { printf 'deployment: %s\n' "$1" >&2; }

COMPOSE_FILE="$HERE/docker-compose.prod.yml"
COMPOSE_ARGS="-p yanki-prod -f $COMPOSE_FILE"

# dc <args...> — run docker compose, wrapping in `sg docker -c` when the current
# shell cannot reach the docker socket directly (no Desktop, group not active in
# this shell). Detected once; the local path stays a faithful rehearsal.
DOCKER_DIRECT=0
if docker info >/dev/null 2>&1; then DOCKER_DIRECT=1; fi
dc() {
  if [ "$DOCKER_DIRECT" -eq 1 ]; then
    docker compose $COMPOSE_ARGS "$@"
  else
    # Re-quote args into one string for `sg docker -c`.
    local q="" a
    for a in "$@"; do q="$q $(printf '%q' "$a")"; done
    sg docker -c "docker compose $COMPOSE_ARGS$q"
  fi
}

HEALTH_URL="${HEALTH_URL:-https://yanki.beyondkaira.com/healthz}"
HEALTH_EXPECT="${HEALTH_EXPECT:-ok}"
HEALTH_KEY="${HEALTH_KEY:-status}"
HEALTH_TRIES="${HEALTH_TRIES:-45}"
HEALTH_CURL_OPTS="${HEALTH_CURL_OPTS:-}"
DEPLOY_ALLOW_DIRTY="${DEPLOY_ALLOW_DIRTY:-0}"

# health_probe — one bounded curl loop that asserts a REAL signal: the body must
# contain BOTH markers, not merely return 200. Hard-fail after HEALTH_TRIES.
# Returns 0 healthy, 1 never became healthy.
health_probe() {
  local url="$1" body="" i=0
  info "health probe: $url  (expect body to contain \"$HEALTH_KEY\" and \"$HEALTH_EXPECT\")"
  while [ "$i" -lt "$HEALTH_TRIES" ]; do
    i=$((i + 1))
    # shellcheck disable=SC2086
    body="$(curl -fsS --max-time 10 $HEALTH_CURL_OPTS "$url" 2>/dev/null || true)"
    if printf '%s' "$body" | grep -q "$HEALTH_KEY" \
       && printf '%s' "$body" | grep -q "$HEALTH_EXPECT"; then
      info "healthy after ${i} attempt(s)"
      return 0
    fi
    sleep 2
  done
  oops "not healthy after ${HEALTH_TRIES} attempts (~$((HEALTH_TRIES * 2))s): $url"
  return 1
}

# ---------------------------------------------------------------------------
# 1. preflight
# ---------------------------------------------------------------------------
say "1/7 preflight"

for tool in git curl docker; do
  command -v "$tool" >/dev/null 2>&1 || { oops "$tool is not on PATH"; exit 1; }
done

if [ ! -f "$HERE/.env" ]; then
  oops "$HERE/.env is missing."
  oops "  cp deploy/.env.example deploy/.env and fill in real secrets first."
  oops "  deployment.sh never auto-creates secrets."
  exit 1
fi

# Fail fast if a live (DRY_RUN=0) deploy is missing LLM keys — /healthz never
# calls a provider, so without this the deploy reports OK and jobs fail at runtime.
if ! python3 "$REPO_ROOT/scripts/check_env.py" "$HERE/.env"; then
  oops "deploy/.env failed check_env.py (see above). Refusing to deploy."
  exit 1
fi

git -C "$REPO_ROOT" rev-parse --git-dir >/dev/null 2>&1 || {
  oops "not a git checkout — there is no SHA to deploy or roll back to"
  exit 1
}
if [ "$DEPLOY_ALLOW_DIRTY" != "1" ] && [ -n "$(git -C "$REPO_ROOT" status --porcelain)" ]; then
  oops "the working tree is dirty."
  git -C "$REPO_ROOT" status --short >&2
  oops "  a deploy from a dirty tree produces an image no SHA describes, which makes"
  oops "  the .last-good rollback a lie. Commit or stash first (or DEPLOY_ALLOW_DIRTY=1)."
  exit 1
fi

GIT_SHA="$(git -C "$REPO_ROOT" rev-parse --short HEAD)"
export GIT_SHA

# The rollback point is whatever .last-good currently records — read BEFORE we
# change anything, so a failed apply/health can restore it.
PREVIOUS=""
if [ -f "$HERE/.last-good" ]; then
  PREVIOUS="$(tr -d '[:space:]\r' < "$HERE/.last-good" || true)"
fi

info "deploying    : $GIT_SHA"
info "previous good: ${PREVIOUS:-none (first deploy)}"
info "compose      : docker compose $COMPOSE_ARGS  ($([ "$DOCKER_DIRECT" -eq 1 ] && echo direct || echo 'via sg docker'))"
info "health url   : $HEALTH_URL"

if [ "$CHECK_ONLY" -eq 1 ]; then
  say "--check"
  info "would build images yanki-api:$GIT_SHA / yanki-web:$GIT_SHA"
  info "would migrate (one-shot alembic upgrade head), then compose up -d"
  info "would health-probe $HEALTH_URL, rolling back to ${PREVIOUS:-none} on failure"
  # Validate the compose file parses without starting anything.
  if ! dc config -q; then
    oops "docker compose config failed — the prod compose file is not valid."
    exit 1
  fi
  info "compose config: valid"
  printf '\ndeployment --check: preflight passed, compose valid. NOTHING was changed.\n'
  exit 0
fi

# ---------------------------------------------------------------------------
# 1b. Take the machine-wide deploy lock (real runs only; --check exited above).
#
# There are now TWO drivers of the `yanki-prod` compose project: a human running
# this script, and CI's forced command (~/.local/bin/yanki-ci-deploy) after a
# merge to main. Both build sha-tagged images and `compose up -d` the same
# project, so running them at once interleaves two releases — the surviving
# containers and the recorded .last-good can end up describing different code.
#
# One lock file, in $HOME so both paths resolve it identically. The CI wrapper
# takes it BEFORE it checks out a sha (that part has to be inside the lock too)
# and passes YANKI_DEPLOY_LOCK_HELD=1 so we do not deadlock against it here.
# ---------------------------------------------------------------------------
if [ "${YANKI_DEPLOY_LOCK_HELD:-0}" != "1" ]; then
  LOCK_FILE="${YANKI_DEPLOY_LOCK:-$HOME/.local/state/yanki-prod-deploy.lock}"
  mkdir -p "$(dirname "$LOCK_FILE")"
  exec 9>"$LOCK_FILE"
  if ! flock -w 900 9; then
    oops "another deploy is already running (CI or another shell) — timed out after 900s."
    oops "  Wait for it to finish, or check ~/.local/state/yanki-ci-deploy.log."
    exit 1
  fi
  info "deploy lock: acquired ($LOCK_FILE)"
fi

# The rollback closure — defined before the first step that can need it, invoked
# ONLY from inside an `if !`. Reuses rollback.sh (the corpus reference for
# .last-good rollback) for the compose mechanics, then re-asserts PUBLIC health
# so a rollback that does not actually restore service still exits non-zero.
rollback() {
  if [ -z "$PREVIOUS" ]; then
    oops "no .last-good to roll back to (first deploy?). The stack is in whatever"
    oops "  state the failed step left it — this is the manual-intervention case."
    return 1
  fi
  printf '\n== rolling back to last-good %s\n' "$PREVIOUS" >&2
  if ! "$HERE/rollback.sh"; then
    oops "rollback.sh FAILED. Manual intervention is required now."
    return 1
  fi
  if ! health_probe "$HEALTH_URL"; then
    oops "rolled back to $PREVIOUS but it is NOT healthy at the edge. Manual intervention."
    return 1
  fi
  return 0
}

# ---------------------------------------------------------------------------
# 2. build
# ---------------------------------------------------------------------------
say "2/7 build"
if ! dc build; then
  oops "the build failed. Nothing has been deployed."
  exit 1
fi
info "built yanki-api:$GIT_SHA / yanki-web:$GIT_SHA"

# ---------------------------------------------------------------------------
# 3. last-good (rollback point already captured in \$PREVIOUS above)
# ---------------------------------------------------------------------------
say "3/7 rollback point"
info "rollback target is ${PREVIOUS:-none (first deploy)}"

# ---------------------------------------------------------------------------
# 4. migrate — BEFORE any container is replaced (issue #16)
# ---------------------------------------------------------------------------
# The api used to migrate on boot. That fused a schema change to a container
# swap, with two consequences: a bad migration took the site down before anyone
# could see it, and a GOOD migration made rollback impossible (the previous
# image's alembic exits 255 on a revision it has never heard of).
#
# Running it here, against the still-serving old stack, inverts both. A failed
# migration now costs nothing: the previous release is still up, and we exit
# without touching it. A successful one leaves a schema the old code can still
# serve, because it only ever adds.
say "4/7 migrate"
if ! dc up -d --wait db; then
  oops "the database did not come up. Nothing has been deployed."
  exit 1
fi
if ! dc run --rm --no-deps api alembic upgrade head; then
  oops "the migration failed. NOTHING has been deployed — the previous release"
  oops "  ($PREVIOUS) is still serving and the schema is unchanged."
  exit 1
fi
info "schema migrated to head"

# ---------------------------------------------------------------------------
# 5. apply — compose up (containers serve; they no longer migrate)
# ---------------------------------------------------------------------------
say "5/7 apply"
if ! dc up -d; then
  oops "compose up failed."
  if rollback; then oops "rolled back to $PREVIOUS."; fi
  exit 1
fi
info "stack up — new containers running $GIT_SHA"

# ---------------------------------------------------------------------------
# 5. health — against the PUBLIC url (proves the nginx path-split serves)
# ---------------------------------------------------------------------------
say "6/7 health"
if ! health_probe "$HEALTH_URL"; then
  oops "the deployed release is not healthy at the edge."
  if rollback; then oops "rolled back to $PREVIOUS."; fi
  exit 1
fi

# ---------------------------------------------------------------------------
# 6. record — only now is this SHA the known-good one
# ---------------------------------------------------------------------------
say "7/7 record"
printf '%s\n' "$GIT_SHA" > "$HERE/.last-good"
info "recorded .last-good = $GIT_SHA"

printf '\ndeployment: yanki @ %s is live at %s and healthy.\n' "$GIT_SHA" "$HEALTH_URL"
