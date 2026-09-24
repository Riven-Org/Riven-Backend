.PHONY: install up down api worker migrate test lint fmt typecheck check

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
	uv run mypy apps/api/src apps/worker/src packages/schemas/src

check: lint typecheck test   ## Everything CI runs
