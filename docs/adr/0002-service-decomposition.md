# ADR 0002: Service decomposition and data ownership

- **Status:** Accepted
- **Date:** 2026-09-27
- **Ticket:** S01.1

## Context

The MVP pipeline (capture → analyze → sandbox → verify → memory → graph) must grow into a
platform without re-architecture. Each part needs a clear owner for its data and a versioned
contract with the others, so one part can change without silently breaking another.

## Decision

Riven is split into eight **logical services**. At current scale they are deployed as two
processes (`apps/api` and `apps/worker`) plus the web app; a service can later move into its
own process without changing its contracts.

| Service | ADR | Runs in | Owns (tables / stores) | Publishes |
|---|---|---|---|---|
| api-gateway | [0003](0003-service-api-gateway.md) | `apps/api` | users, organizations, memberships, invitations, service accounts, API keys | — |
| capture | [0004](0004-service-capture.md) | `apps/api` | repositories, changes | `change.captured` |
| orchestrator | [0005](0005-service-orchestrator.md) | `apps/worker` | verification runs (+ Temporal history) | `verification.completed` |
| sandbox-runner | [0006](0006-service-sandbox-runner.md) | `apps/worker` | run artifacts (object storage) | — |
| verifier | [0007](0007-service-verifier.md) | `apps/worker` | findings | — |
| memory | [0008](0008-service-memory.md) | `apps/worker` | bugs, regression locks | `bug.confirmed`, `regression.detected`, `lock.created` |
| graph | [0009](0009-service-graph.md) | `apps/worker` | graph nodes, graph edges | — |
| web | [0010](0010-service-web.md) | Riven-Frontend | nothing | — |

Rules every service follows:

1. **One writer per table.** Only the owning service writes its tables. Others read through
   the owner's API/module or react to its events.
2. **Contracts live in `packages/schemas`.** Every payload crossing a boundary (HTTP, Temporal
   activity input/output, domain event) is a Pydantic model in `riven_schemas`, exported as
   JSON Schema and guarded by contract tests (a breaking change fails CI unless the schema
   version is bumped).
3. **Events go through the transactional outbox** (S01.3): written in the same transaction as
   the state change, delivered at least once, handled idempotently.
4. **Every row is tenant-scoped** by `org_id` (S01.4, S03.2).
5. **Independence:** the identity that produced a change is never the identity that verifies it.

## Consequences

- Splitting a service into its own deployment is a packaging change, not a redesign.
- Cross-service joins in SQL are not allowed; a read model is built from events instead.
- Adding a service means adding an ADR here and a row to the table above.
