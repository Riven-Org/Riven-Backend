# ADR 0003: Service boundary — api-gateway

- **Status:** Accepted
- **Date:** 2026-09-27
- **Ticket:** S01.1 (see [ADR 0002](0002-service-decomposition.md))

## Responsibility

The only public entry point. Authenticates every request (user JWT or API key), resolves the organization, enforces role permissions, and routes to the owning service. Hosts the versioned REST API under `/v1`.

## Runs in

apps/api (`riven_api.routers`, auth dependencies)

## Owns

`users`, `organizations`, `memberships`, `invitations`, `service_accounts`, `api_keys` (E03).

## Publishes

None (audit events arrive with S04.4).

## Consumes

None.

## Does not

Business rules of other services. Routers stay thin and call the owning service's module.
