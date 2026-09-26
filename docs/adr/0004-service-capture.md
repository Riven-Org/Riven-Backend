# ADR 0004: Service boundary — capture

- **Status:** Accepted
- **Date:** 2026-09-27
- **Ticket:** S01.1 (see [ADR 0002](0002-service-decomposition.md))

## Responsibility

Receives changes from source hosts (GitHub App webhooks, CLI/agent submissions), records who produced them, and starts a verification run.

## Runs in

apps/api (webhook receivers, later its own process)

## Owns

`repositories`, `changes` (including the authenticated producer identity).

## Publishes

`change.captured`.

## Consumes

None.

## Does not

Running or judging code. Capture never decides a verdict.
