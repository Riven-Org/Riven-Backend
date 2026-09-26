# ADR 0008: Service boundary — memory

- **Status:** Accepted
- **Date:** 2026-09-27
- **Ticket:** S01.1 (see [ADR 0002](0002-service-decomposition.md))

## Responsibility

Institutional memory: fingerprints failures, recognises recurring bugs, manages the bug lifecycle and turns fixed bugs into regression locks that are re-run on related changes.

## Runs in

apps/worker activities

## Owns

`bugs`, `bug_occurrences`, `regression_locks`.

## Publishes

`bug.confirmed`, `regression.detected`, `lock.created`.

## Consumes

`verification.completed`.

## Does not

Graph storage; memory emits events and the graph service links them.
