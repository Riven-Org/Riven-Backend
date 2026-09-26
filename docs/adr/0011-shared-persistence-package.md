# ADR 0011: Shared persistence package and object storage

- **Status:** Accepted
- **Date:** 2026-09-27
- **Ticket:** S01.4

## Context

ADR 0002 gives tables to services that run in the worker (orchestrator, memory, graph), but
the SQLAlchemy models lived in `apps/api`. The worker would have had to import the whole API
app to write its own tables. Run logs and artifacts also need a home outside local disk so
any process can serve them.

## Decision

- **`packages/db` (`riven_db`)** holds `Base`, `TenantMixin` and every domain model, one
  module per owning service (`models/capture.py`, `runs.py`, `memory.py`, `graph.py`). Both
  apps import it. Alembic stays in `apps/api/alembic` and migrates `riven_db` plus
  `riven_events` metadata. A test compares a freshly migrated database with the models, so a
  model change without a migration fails CI.
- Every domain table has a non-null, indexed `org_id` from its first migration (there is no
  existing data to backfill), ready for row-level security in S03.2.
- **`packages/storage` (`riven_storage`)** is the only way services store logs and
  artifacts: an S3-compatible bucket (MinIO locally, S3 in the cloud) under
  `<org_id>/<run_id>/<name>` keys, downloaded through presigned URLs (15 minutes by default).
  The `artifacts` table keeps the metadata. A test fails if service code writes to local
  disk.
- The causal graph's consistency check runs nightly as a Temporal Schedule
  (`graph-consistency-nightly`, 03:00 UTC) that the worker registers at startup.

## Consequences

- One ownership rule still applies: a service writes only its own module's tables.
- `apps/api/src/riven_api/models/` is not used; `CLAUDE.md` points to `riven_db`.
