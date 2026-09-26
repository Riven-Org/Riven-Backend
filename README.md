# Riven Backend

Independent verification and institutional memory for AI-built software.
**Verify. Remember. Learn from every change.**

The dashboard lives in [Riven-Frontend](https://github.com/Riven-Org/Riven-Frontend).

## Repository layout

```
apps/
  api/        FastAPI service (public API, health checks, Alembic migrations)
  worker/     Temporal worker: the verification pipeline and scheduled jobs
packages/
  schemas/    Shared Pydantic contracts and domain events (+ JSON Schema baselines)
  events/     Transactional outbox, Redis Streams relay, idempotent consumers
  db/         SQLAlchemy models for every service's tables, demo seed
  storage/    Object storage for run logs and artifacts (MinIO / S3)
docs/adr/     Architecture decision records
docs/events.md  Event catalog (generated)
```

Architecture: [ADR 0002 service decomposition](docs/adr/0002-service-decomposition.md) and the
other records in [docs/adr](docs/adr).

## Setup in five steps

You need **Docker with Compose v2.20+**, **Python 3.12** and **[uv](https://docs.astral.sh/uv/)**
(`curl -LsSf https://astral.sh/uv/install.sh | sh`). Ports 5432, 6379, 7233, 8000, 8080, 9000
and 9001 must be free.

1. **Clone and configure**
   ```bash
   git clone https://github.com/Riven-Org/Riven-Backend.git && cd Riven-Backend
   cp .env.example .env
   ```
2. **Install the Python tooling** (for tests and editors; the stack itself runs in Docker)
   ```bash
   make install
   ```
3. **Start everything**
   ```bash
   make dev
   ```
   This starts Postgres, Redis, MinIO and Temporal, waits until they are healthy, creates the
   artifacts bucket, applies migrations, starts the API, worker and outbox relay, and loads the
   demo org. The first run builds the image and takes a few minutes.
4. **Check it works**
   ```bash
   curl localhost:8000/health/ready     # {"status":"ok","database":"up"}
   docker compose ps                    # every service running or healthy
   ```
   | Service | URL | Login |
   |---|---|---|
   | API docs | http://localhost:8000/docs | — |
   | Temporal UI | http://localhost:8080 | — |
   | MinIO console | http://localhost:9001 | `riven` / `riven-dev-secret` |
5. **Run the checks CI runs**
   ```bash
   make check
   ```

### Demo data

`make dev` seeds the org `demo` with the repository `riven-demo/shop`: five changes from a human,
an AI agent and a bot, the bug an AI change introduced ("Tokens expire one second early"), its
fix and regression lock, a later change that brought the bug back, and the causal graph that
links requirement → change → module → bug → fix → test. Seeding again is a no-op; to start over,
run `docker compose down -v && make dev`.

## Developing against the stack

Run infrastructure in Docker and the app on your machine with hot reload:

```bash
docker compose stop api worker relay   # if `make dev` started them
make up          # Postgres, Redis, MinIO, Temporal only
make migrate     # apply migrations to the database in .env
make seed        # demo data (optional)
make api         # http://localhost:8000 with reload
make worker      # Temporal worker (second terminal)
make relay       # outbox → Redis Stream (third terminal)
```

### Database tests

Tests that need Postgres are skipped unless `RIVEN_TEST_DATABASE_URL` points at a **disposable**
database (the tests drop and recreate its schema):

```bash
docker compose exec postgres createdb -U riven riven_test
RIVEN_TEST_DATABASE_URL=postgresql+asyncpg://riven:riven@localhost:5432/riven_test make test
```

CI always runs them against Postgres and Redis service containers.

## Everyday commands

| Command | What it does |
|---|---|
| `make dev` | Whole stack in Docker with demo data |
| `make up` / `make down` | Infrastructure only / stop everything (volumes kept) |
| `make migrate` | Apply migrations |
| `make seed` | Load the demo org (idempotent) |
| `make test` | Run all tests |
| `make lint` / `make fmt` | Ruff lint + format check / auto-fix |
| `make typecheck` | mypy (strict) |
| `make check` | Everything CI runs |
| `make catalog` | Regenerate `docs/events.md` after changing an event |
| `make schemas` | Export contracts as JSON Schema to `build/json-schema` |

New migration: `uv run alembic -c apps/api/alembic.ini revision --autogenerate -m "<ID>: <what>"`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `port is already allocated` | Another Postgres/Redis is running locally. Stop it (`sudo systemctl stop postgresql`) or change the host port in `docker-compose.yml`. |
| `make dev` stops at `temporal` | Temporal needs ~30 s on first start to create its databases. Run `make dev` again; check `docker compose logs temporal`. |
| `unknown flag: --wait` | Compose is too old. Install Docker Compose v2.20 or newer. |
| API `/health/ready` returns 503 | Postgres is not reachable with `RIVEN_DATABASE_URL`. Inside Docker the host is `postgres`; on your machine it is `localhost`. |
| `relation ... does not exist` | Migrations have not run: `make migrate` (or `docker compose --profile init run --rm migrate`). |
| Database tests are all skipped | Set `RIVEN_TEST_DATABASE_URL` (see Database tests). |
| `test_fresh_database_at_head_matches_the_models` fails | You changed a model without a migration. Autogenerate one (see above). |
| `test_contract_is_backward_compatible_with_baseline` fails | You made a breaking change to a shared contract. Make it additive, or bump `SCHEMA_VERSION` and snapshot a new baseline. |
| Anything else | `docker compose down -v && make dev` resets all local data. |

## Working on a ticket

Tickets live in `docs/tickets/`. Branch from the latest `main` as `<ticket-id>-<slug>`, make the
change with tests, run `make check`, push the branch and open a PR with the ticket ID in the
description. See `CLAUDE.md` for the full workflow.
