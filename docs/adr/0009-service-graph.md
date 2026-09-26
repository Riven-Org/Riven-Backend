# ADR 0009: Service boundary — graph

- **Status:** Accepted
- **Date:** 2026-09-27
- **Ticket:** S01.1 (see [ADR 0002](0002-service-decomposition.md))

## Responsibility

Maintains the causal graph (requirement → change → module → bug → fix → test). Every edge carries provenance (source, confidence, created_by, valid_from/valid_to); edges are closed, never deleted. Traversals use recursive CTEs.

## Runs in

apps/worker (event consumer) + one org-scoped repository module

## Owns

`graph_nodes`, `graph_edges` (PostgreSQL, see ADR 0001).

## Publishes

None.

## Consumes

All domain events.

## Does not

Raw graph SQL outside its repository module.
