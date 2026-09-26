.PHONY: install dev seed up down api worker relay migrate test lint fmt typecheck check schemas catalog

install:        ## Install dependencies and git hooks
	uv sync
	uv run pre-commit install

dev:            ## Whole stack in Docker: infra, migrations, API, worker, relay, demo data
	docker compose up -d --wait postgres redis minio temporal
	docker compose --profile init run --rm minio-init
	docker compose --profile init run --rm --build migrate
	docker compose up -d --wait api worker relay temporal-ui
	docker compose run --rm api python -m riven_db.seed
	@echo "API http://localhost:8000/docs · Temporal UI http://localhost:8080 · MinIO http://localhost:9001"

seed:           ## Load the demo org into the database from .env (idempotent)
	uv run python -m riven_db.seed

up:             ## Start only the infrastructure (Postgres, Redis, MinIO, Temporal) for local runs
	docker compose up -d --wait postgres redis minio temporal
	docker compose --profile init run --rm minio-init

down:           ## Stop the stack (data volumes are kept; `docker compose down -v` wipes them)
	docker compose down

api:            ## Run the API on :8000 with reload
	uv run uvicorn riven_api.main:app --reload --port 8000

worker:         ## Run the Temporal worker
	uv run python -m riven_worker.main

relay:          ## Publish outbox events to the Redis Stream
	uv run python -m riven_events.relay

catalog:        ## Regenerate docs/events.md from the schema package
	uv run python -m riven_schemas.catalog > docs/events.md

migrate:        ## Apply database migrations
	uv run alembic -c apps/api/alembic.ini upgrade head

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .

fmt:
	uv run ruff check --fix .
	uv run ruff format .

typecheck:
	uv run mypy apps/api/src apps/worker/src packages/schemas/src packages/events/src packages/db/src packages/storage/src

check: lint typecheck test   ## Everything CI runs

schemas:        ## Export contracts as JSON Schema to build/json-schema
	uv run python -m riven_schemas.export build/json-schema
