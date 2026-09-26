# ADR 0007: Service boundary — verifier

- **Status:** Accepted
- **Date:** 2026-09-27
- **Ticket:** S01.1 (see [ADR 0002](0002-service-decomposition.md))

## Responsibility

Runs verifier plugins over the sandbox results and diff and applies the verdict policy (`passed`, `failed`, `needs_review`). Enforces independence: the verifier identity differs from the producer.

## Runs in

apps/worker activities

## Owns

`findings`.

## Publishes

None (the orchestrator publishes the verdict).

## Consumes

None.

## Does not

Storing bug history; that is memory's job.
