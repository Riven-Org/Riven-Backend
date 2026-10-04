.PHONY: install api test lint fmt typecheck check

install:        ## Install dependencies and git hooks
	uv sync
	uv run pre-commit install

api:            ## Run the API on :8000 with reload (SQLite file riven.db, created on start)
	uv run uvicorn riven_api.main:app --reload --port 8000

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .

fmt:
	uv run ruff check --fix .
	uv run ruff format .

typecheck:
	uv run mypy apps/api/src

check: lint typecheck test   ## Everything CI runs
