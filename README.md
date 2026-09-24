# Riven Backend

Independent verification and institutional memory for AI-built software.
**Verify. Remember. Learn from every change.**

The dashboard lives in [Riven-Frontend](https://github.com/Riven-Org/Riven-Frontend).

## Repository layout

```
apps/
  api/        FastAPI service (public API, health checks, migrations)
  worker/     Temporal worker: the verification pipeline
packages/
  schemas/    Shared Pydantic contracts and domain events
docs/adr/     Architecture decision records
```

Stack and reasons: [docs/adr/0001-tech-stack.md](docs/adr/0001-tech-stack.md).

## Prerequisites

- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Docker with Docker Compose

## Getting started

```bash
cp .env.example .env
make install     # dependencies + git hooks
make up          # Postgres (pgvector), Redis, MinIO, Temporal
make migrate     # apply database migrations
```

Then, in two terminals:

```bash
make api         # http://localhost:8000  (API docs at /docs)
make worker      # Temporal worker
```

| Service | URL |
|---|---|
| API | http://localhost:8000 |
| Temporal UI | http://localhost:8080 |
| MinIO console | http://localhost:9001 |

## Everyday commands

| Command | What it does |
|---|---|
| `make test` | Run all tests |
| `make lint` | Ruff lint + format check |
| `make fmt` | Auto-fix and format |
| `make typecheck` | mypy (strict) |
| `make check` | Everything CI runs |

## Working on a ticket

1. Branch from `main`: `git checkout -b S01.2-durable-pipeline`
2. Make the change with tests; run `make check`.
3. Open a PR and put the ClickUp ticket ID in the description.
