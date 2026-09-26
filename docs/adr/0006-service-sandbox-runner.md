# ADR 0006: Service boundary — sandbox-runner

- **Status:** Accepted
- **Date:** 2026-09-27
- **Ticket:** S01.1 (see [ADR 0002](0002-service-decomposition.md))

## Responsibility

Builds the change's environment and runs tests in an isolated sandbox with no network egress and capped CPU, memory and time. Classifies infrastructure failures (timeout, OOM) separately from code failures.

## Runs in

apps/worker activities (dedicated worker pool later)

## Owns

Run logs and artifacts in object storage (`artifacts` metadata table from S01.4).

## Publishes

None (returns results to the orchestrator).

## Consumes

None.

## Does not

Deciding whether a failure is a bug. Infrastructure failures never create bugs.
