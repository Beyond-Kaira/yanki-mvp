# Yanki — the single control panel. Run `make` (or `make help`) to list targets.
# Each public target carries a `## description` used by the self-documenting help.

.DEFAULT_GOAL := help

# Test Postgres (started by `make test` when docker is available).
TEST_DB_CONTAINER := yanki-test-db
TEST_DATABASE_URL := postgresql+psycopg://yanki:yanki@localhost:5433/yanki_test

.PHONY: help setup bootstrap dev test lint fmt typecheck migrate gen-types e2e \
        deploy rollback deploy-logs deploy-down backup restore-check

help: ## List all targets (default goal)
	@awk 'BEGIN {FS = ":.*## "; printf "Yanki make targets:\n\n"} \
		/^[a-zA-Z0-9_-]+:.*## / {printf "  \033[36m%-13s\033[0m %s\n", $$1, $$2}' \
		$(MAKEFILE_LIST)
	@printf "\n"

setup: ## Install uv (if missing) + backend/frontend deps + pre-commit hooks
	@command -v uv >/dev/null 2>&1 || { \
		echo ">> installing uv"; curl -LsSf https://astral.sh/uv/install.sh | sh; }
	cd backend && uv sync
	cd frontend && npm install
	@if [ -f .pre-commit-config.yaml ]; then \
		if command -v pre-commit >/dev/null 2>&1; then pre-commit install; \
		else echo ">> .pre-commit-config.yaml present but pre-commit CLI missing — run 'pipx install pre-commit'"; fi; \
	else echo ">> no .pre-commit-config.yaml yet — skipping pre-commit install"; fi

bootstrap: setup ## Alias for `make setup`

dev: ## Start the full dev stack (db + api + worker + web, hot reload)
	docker compose -f deploy/docker-compose.yml --env-file deploy/.env up --build

test: ## Run backend (pytest) + frontend (vitest); starts a throwaway test Postgres
	@set -e; \
	db_started=0; \
	if command -v docker >/dev/null 2>&1; then \
		echo ">> starting test Postgres on :5433"; \
		docker rm -f $(TEST_DB_CONTAINER) >/dev/null 2>&1 || true; \
		docker run -d --name $(TEST_DB_CONTAINER) \
			-e POSTGRES_USER=yanki -e POSTGRES_PASSWORD=yanki -e POSTGRES_DB=yanki_test \
			-p 5433:5432 postgres:16 >/dev/null; \
		db_started=1; \
		echo ">> waiting for Postgres to accept connections"; \
		for i in $$(seq 1 30); do \
			docker exec $(TEST_DB_CONTAINER) pg_isready -U yanki -d yanki_test >/dev/null 2>&1 && break; \
			sleep 1; \
		done; \
	else \
		echo ">> docker not found — skipping test Postgres (DB-dependent tests auto-skip)"; \
	fi; \
	rc=0; \
	( cd backend && DRY_RUN=1 TEST_DATABASE_URL=$(TEST_DATABASE_URL) uv run pytest ) || rc=$$?; \
	( cd frontend && npm test -- --run ) || rc=$$?; \
	if [ $$db_started -eq 1 ]; then \
		echo ">> stopping test Postgres"; docker rm -f $(TEST_DB_CONTAINER) >/dev/null 2>&1 || true; \
	fi; \
	exit $$rc

lint: ## Lint backend (ruff) + frontend (eslint)
	cd backend && uv run ruff check .
	cd frontend && npm run lint

fmt: ## Auto-format backend (ruff format) + frontend (prettier)
	cd backend && uv run ruff format .
	cd frontend && npx prettier --write .

typecheck: ## Type-check backend (mypy) + frontend (tsc --noEmit)
	cd backend && uv run mypy app
	cd frontend && npx tsc --noEmit

migrate: ## Apply Alembic migrations locally (alembic upgrade head)
	cd backend && uv run alembic upgrade head

gen-types: ## Regenerate shared/contracts/openapi.json + checker_methodology.json + frontend/lib/types.ts
	uv run --project backend python scripts/gen_openapi.py
	uv run --project backend python scripts/gen_methodology.py
	cd frontend && npm run gen-types

e2e: ## Run the Playwright happy-path against a running stack (needs `make dev` up)
	E2E_BASE_URL=http://localhost:$${YANKI_WEB_PORT:-8140} npx --prefix frontend playwright test

deploy: ## Build, deploy, migrate + health-check on the server (auto-rollback)
	./deploy/deploy.sh

rollback: ## Redeploy the last-good release SHA
	./deploy/rollback.sh

deploy-logs: ## Tail logs from the running prod stack
	./deploy/deploy-logs.sh

deploy-down: ## Stop the prod stack (keeps data volumes)
	./deploy/deploy-down.sh

backup: ## Take one verified dump of the prod database (see deploy/BACKUP.md)
	./deploy/backup.sh

restore-check: ## Restore the newest dump into a throwaway DB and assert it is real
	./deploy/restore-check.sh
