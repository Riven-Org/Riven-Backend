# ADR 0013: Identity and access

- **Status:** Accepted
- **Date:** 2026-09-27
- **Tickets:** E03 (S03.1–S03.5)

## Sign-in (S03.1)

- **Keycloak** (open source, self-hosted, free) is the identity provider; WorkOS was the paid
  alternative. The realm is code: `infra/keycloak/realm-riven.json`, imported at startup.
  Values that differ per environment are `${VAR:default}` placeholders.
- Users sign up with email + password (email verification required; Mailpit catches mail in
  development) or with GitHub / Google (their verified email is trusted). Brute-force
  protection and a 12-character password policy are on.
- The dashboard is the public client `riven-web` using authorization code + **PKCE (S256)**.
  An audience mapper adds `riven-api` to its access tokens. Access tokens live 5 minutes;
  refresh tokens rotate and cannot be reused.
- **The API validates every request's JWT**: signature against the realm's JWKS (cached ten
  minutes, refreshed early when an unknown key id appears, at most every 30 seconds),
  `exp`, `iss`, `aud = riven-api`, `typ = Bearer`, and `email_verified = true`. Failures are
  401 (403 for an unverified email).
- Users are provisioned in `users` on first sign-in, keyed by the IdP subject.
- `riven-api` is a confidential client whose service account may view and manage users; the
  API uses it for session and MFA administration (S03.5).

Identity tables (`users`, and later memberships, invitations, service accounts, API keys) are
global rather than row-level-secured: authentication must find them before an org context
exists. The identity service always filters them explicitly.

## Organizations and tenant isolation (S03.2)

- An **organization** (`org_<hex>`) is the tenant. Users join through **memberships** with one
  role; owners and admins invite by email (7-day, single-use token stored as a SHA-256 hash;
  the invitee's email must match).
- Org endpoints live under `/v1/orgs/{org_id}/…`. Non-members get **404**, the same as for an
  org that does not exist, so ids cannot be probed.
- **Postgres row-level security** on every tenant table (`riven_db.tenant_tables()`): policy
  `tenant_isolation` compares `org_id` with `current_setting('app.org_id')`. Request
  transactions of a `tenant_session` run `SET LOCAL ROLE riven_app` and set `app.org_id`
  (a SQLAlchemy `after_begin` hook, so every transaction gets it and a pooled connection never
  keeps it). Without an org context a query returns zero rows; writing another org's row
  fails. System jobs (migrations, seed, relay, nightly checks) use the login role, which owns
  the tables and is not subject to RLS. New tenant tables call `enable_rls()` in their
  migration; a test fails otherwise.
- **Graph access** goes only through `riven_db.graph_repository.GraphRepository(session,
  org_id)`, which filters every query by org on top of RLS. A test fails if any other source
  file mentions the graph tables or models.
- `test_cross_tenant.py` discovers every `/v1/orgs/{org_id}` endpoint from the OpenAPI schema
  and calls it as a member of another org; anything but 403/404 fails CI.

## Roles and permissions (S03.3)

- Five roles, nested: **viewer** (read) ⊂ **reviewer** (+ confirm bugs, approve reviews) ⊂
  **maintainer** (+ submit changes, manage repos, create locks, see API keys) ⊂ **admin**
  (+ members, API keys, security policy, retire locks, audit) ⊂ **owner** (everything,
  including deleting the org). The matrix is code (`riven_api.auth.permissions`) and
  documentation (`docs/permissions.md`, generated; a test fails when stale). Casbin was not
  needed for a static matrix.
- **Deny by default:** `PermissionedRoute` refuses to build a `/v1` route that does not
  declare `require(Permission.…)`, depend on the caller only (`authenticated`), or mark itself
  public. The declaration is published as `x-riven-permission` in OpenAPI, and a test calls
  every org endpoint as every role that lacks its permission and expects 403.
- Only owners manage owners, and an org always keeps one owner.
- Org responses include the caller's `permissions`, so the dashboard hides actions without
  re-implementing the rules; the API stays the authority.

## Service accounts and API keys (S03.4)

- A **service account** is a non-human identity bound to one org, of kind `ai_agent`, `ci` or
  `bot` (with an optional agent model). It authenticates with **API keys**
  `rvn_<prefix>_<secret>`: the prefix is stored for lookup, the secret only as an **Argon2**
  hash, and the full key is returned once, at creation or rotation.
- Every key has **scopes** (permissions from the matrix, defaulting per kind) that must be a
  subset of what its creator holds, an optional expiry (90 days by default) and
  `last_used_at`. Rotation issues a new secret with the same scopes and lifetime and revokes
  the old one; disabling an account revokes all its keys.
- Revocation, expiry and disabled accounts are checked on **every** request, so a revoked key
  fails on its next use. Successful Argon2 checks are cached in memory for 60 s to keep
  hashing off the hot path; the cache never bypasses the revocation checks.
- **Producer identity:** `POST /v1/orgs/{org}/changes` records the producer from the
  credentials (person → `human`/email; service account → `ai_agent` or `bot`/`sa:<name>` and
  model). The body cannot name a producer (unknown fields are rejected), and the change's
  `change.captured` event is written to the outbox in the same transaction.
