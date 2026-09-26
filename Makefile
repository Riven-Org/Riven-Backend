.PHONY: install up down api worker relay migrate test lint fmt typecheck check schemas catalog

install:        ## Install dependencies and git hooks
	uv sync
	uv run pre-commit install

up:             ## Start Postgres, Redis, MinIO, Temporal
	docker compose up -d

down:
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
