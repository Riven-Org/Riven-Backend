# ADR 0005: Service boundary — orchestrator

- **Status:** Accepted
- **Date:** 2026-09-27
- **Ticket:** S01.1 (see [ADR 0002](0002-service-decomposition.md))

## Responsibility

Drives one verification run through its stages as a durable Temporal workflow: retries, timeouts, cancellation and idempotency per (org, repo, commit).

## Runs in

apps/worker (`VerificationWorkflow`)

## Owns

`verification_runs` and the Temporal workflow history.

## Publishes

`verification.completed`.

## Consumes

`change.captured` (starts a run).

## Does not

Stage logic. The workflow only orchestrates; every stage is an activity owned by another service.
