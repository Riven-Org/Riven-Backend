# ADR 0001: Tech stack

- **Status:** Accepted
- **Date:** 2026-09-24

## Decision

| Part | Choice |
|---|---|
| API | Python 3.12, FastAPI, Pydantic v2 |
| Database access | SQLAlchemy 2.0 (async) + Alembic migrations |
| Workflows | Temporal (no Celery) |
| Database | PostgreSQL 16 + pgvector |
| Causal graph | Stored in PostgreSQL (nodes/edges tables), no Neo4j at MVP scale |
| Cache | Redis |
| Artifacts | MinIO locally, S3 in the cloud |
| Frontend | React + Vite + TypeScript, in the separate [Riven-Frontend](https://github.com/Riven-Org/Riven-Frontend) repo |
| Sandbox | Docker now, gVisor before external customers (S20.1) |
| Tooling | uv, ruff, mypy (strict), pytest, GitHub Actions (frontend: npm, oxlint) |

## Why

- **FastAPI over Django:** the team prefers FastAPI; typed Pydantic models are shared
  by the API, the Temporal workers and the AI code; async suits many parallel LLM calls.
  Cost: login, orgs, roles and admin must be assembled (about 1–2 extra sprints in Phase 2).
- **Temporal only:** the pipeline must survive crashes and retry stages. A second job system
  (Celery) would duplicate this.
- **Graph in Postgres:** the MVP graph is modest. Recursive queries are enough, and one
  database is cheaper to run. Revisit if graph queries exceed ~200 ms p95 (S19.4).

## Consequences

Backlog tickets that mention Neo4j or Cypher (S01.4.4, S03.2.3, S09.1, S19.4.4) are
implemented against Postgres tables instead.
