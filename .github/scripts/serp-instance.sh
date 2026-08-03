#!/usr/bin/env bash
#
# Boot (or tear down) a SearXNG instance for the SERP integration tests.
#
# The instance federates exactly ONE engine: the stdlib fixture server in
# backend/tests/integration/searxng/. That is the whole point — the public
# engines SearXNG normally queries (Google, Brave, DuckDuckGo, Startpage) refuse
# CI runners, so an integration test against them would be a coin flip. With the
# fixture engine the results are fixed AND the failure modes are summonable, so
# the tests can assert the honesty rule (an unreadable page is never a miss)
# against real SearXNG rather than against a mock of it.
#
# Run it locally exactly as CI does:
#
#   .github/scripts/serp-instance.sh up
#   cd backend && SERP_TEST_BASE_URL=http://127.0.0.1:19099 uv run pytest tests/integration
#   .github/scripts/serp-instance.sh down
#
# Env: SEARXNG_IMAGE (default: the pinned tag below), SERP_TEST_PORT (19099).
set -euo pipefail

NETWORK=yanki-serp-net
FIXTURE=yanki-serp-fixture
INSTANCE=yanki-serp-searxng
PORT="${SERP_TEST_PORT:-19099}"
# Pinned by default: the PR gate must not turn red because upstream shipped a
# release overnight. The scheduled `upstream drift` job is what runs :latest.
IMAGE="${SEARXNG_IMAGE:-searxng/searxng:2026.8.1-8892414dc}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FIXTURE_DIR="${REPO_ROOT}/backend/tests/integration/searxng"
# The rendered settings file has to outlive `up` — it is bind-mounted, so the
# container needs it on disk for its whole life. Kept in one directory so `down`
# can take it away again rather than leaving it in /tmp forever.
STATE_DIR="${TMPDIR:-/tmp}/yanki-serp-instance"

down() {
  docker rm -f "${INSTANCE}" "${FIXTURE}" >/dev/null 2>&1 || true
  docker network rm "${NETWORK}" >/dev/null 2>&1 || true
  rm -rf "${STATE_DIR}"
}

up() {
  down
  docker network create "${NETWORK}" >/dev/null

  # The committed settings.yml carries a placeholder where SearXNG wants a
  # secret_key. It is generated here instead: this repo is public and CI scans
  # its full history with gitleaks, so a literal key would be both a lie and a
  # build failure.
  #
  # The generated value is world-readable (644, so the container's own user can
  # read the bind mount) and that is fine: it signs sessions for a throwaway
  # instance that federates a fixture server and is destroyed at the end of the
  # job. It guards nothing. `down` removes it either way.
  mkdir -p "${STATE_DIR}"
  chmod 755 "${STATE_DIR}"
  settings="${STATE_DIR}/settings.yml"
  sed "s/REPLACED_AT_RUNTIME/$(openssl rand -hex 32)/" "${FIXTURE_DIR}/settings.yml" >"${settings}"
  chmod 644 "${settings}"

  # The fixture runs on the SearXNG image purely so the job pulls one image
  # rather than two; it is stdlib-only Python and uses nothing from it. On a
  # user-defined bridge, container-name DNS resolves automatically — which is
  # how settings.yml reaches it at http://yanki-serp-fixture:8000.
  docker run -d --name "${FIXTURE}" --network "${NETWORK}" \
    -v "${FIXTURE_DIR}/fixture_engine.py:/fixture_engine.py:ro" \
    --entrypoint python3 "${IMAGE}" /fixture_engine.py 8000 >/dev/null

  docker run -d --name "${INSTANCE}" --network "${NETWORK}" \
    -p "127.0.0.1:${PORT}:8080" \
    -v "${settings}:/etc/searxng/settings.yml:ro" \
    "${IMAGE}" >/dev/null

  # Poll a real JSON search rather than /healthz. An instance answers /healthz
  # while its JSON format is still off, and that misconfiguration is precisely
  # what these tests must not mistake for a code bug. Cold start is ~10-12s.
  for _ in $(seq 1 45); do
    if curl -fsS "http://127.0.0.1:${PORT}/search?q=readycheck&format=json" >/dev/null 2>&1; then
      echo "searxng ready on 127.0.0.1:${PORT} (${IMAGE})"
      return 0
    fi
    sleep 2
  done

  echo "searxng never answered a JSON search on 127.0.0.1:${PORT}" >&2
  docker logs "${INSTANCE}" >&2 || true
  docker logs "${FIXTURE}" >&2 || true
  return 1
}

case "${1:-up}" in
  up) up ;;
  down) down ;;
  *)
    echo "usage: $0 [up|down]" >&2
    exit 2
    ;;
esac
