# ADR 0010: Service boundary — web

- **Status:** Accepted
- **Date:** 2026-09-27
- **Ticket:** S01.1 (see [ADR 0002](0002-service-decomposition.md))

## Responsibility

The dashboard: follows runs live, reviews `needs_review` runs, browses bug memory and locks, explores the graph, manages org, members, roles and keys.

## Runs in

Riven-Frontend (React + Vite)

## Owns

Nothing. All state comes from the API.

## Publishes

None.

## Consumes

The public REST API (OpenAPI contract).

## Does not

Verdict, permission or tenancy logic; the API is the authority.
