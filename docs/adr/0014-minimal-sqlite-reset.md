# ADR 0014: Reset to a minimal SQLite app

- **Status:** Accepted
- **Date:** 2026-10-04
- **Supersedes for now:** ADRs 0001–0013 (removed from the tree; see git history)

## Decision

The backend is cut back to one FastAPI service with:

- SQLite through SQLAlchemy async (`aiosqlite`); tables are created on startup, no migrations yet.
- Email + password accounts: Argon2 password hashes and HS256 JWT bearer tokens.
- Endpoints: `/health`, `/health/ready`, `POST /v1/auth/signup`, `POST /v1/auth/login`, `GET /v1/me`.

Removed: Keycloak and the realm theme, Postgres + row-level security, organizations, roles,
API keys and service accounts, Temporal worker, outbox/Redis events, object storage, shared
schema contracts, Docker Compose.

## Why

The product owner wants a small working base (sign-up, login, dashboard) before rebuilding the
platform. All removed code stays in git history on `main` before this change and can be brought
back ticket by ticket.

## Consequences

- When the schema starts changing, add Alembic back (SQLite supports it with batch mode).
- Moving to Postgres later is a `RIVEN_DATABASE_URL` change plus a driver; keep queries portable.
- The JWT secret must be set in any deployed environment (settings refuse the dev default).
