# Riven Backend

Independent verification and institutional memory for AI-built software.
**Verify. Remember. Learn from every change.**

The dashboard lives in [Riven-Frontend](https://github.com/Riven-Org/Riven-Frontend).

## Repository layout

```
apps/api/     FastAPI service: health checks, email + password auth, SQLite
docs/adr/     Architecture decision records (0014: why the app was reset to this)
```

## Setup

You need **Python 3.12** and **[uv](https://docs.astral.sh/uv/)**
(`curl -LsSf https://astral.sh/uv/install.sh | sh`). No database server or Docker is needed.

```bash
git clone https://github.com/Riven-Org/Riven-Backend.git && cd Riven-Backend
cp .env.example .env
make install
make api            # http://localhost:8000/docs — creates ./riven.db on first start
```

## API

| Method | Path | |
|---|---|---|
| GET | `/health` | Liveness |
| GET | `/health/ready` | Database reachable |
| POST | `/v1/auth/signup` | `{name, email, password}` → `{access_token, user}` |
| POST | `/v1/auth/login` | `{identifier, password}` (email, or the dev username) → `{access_token, user}` |
| GET | `/v1/me` | Current user (`Authorization: Bearer <token>`) |

In development the API creates an account on startup: username **Abubakar**, password **12345**
(email `abubakar@riven.local`). Turn it off with `RIVEN_DEMO_USER_ENABLED=false`; staging and prod
refuse to start while it is on.

## Everyday commands

```bash
make check    # what CI runs: ruff, mypy --strict, pytest
make test
make fmt
```

## Working on a ticket

Tickets live in `docs/tickets/`. Branch from the latest `main` as `<ticket-id>-<slug>`, make the
change with tests, run `make check`, push the branch and open a PR with the ticket ID in the
description. See `CLAUDE.md` for the full workflow.
