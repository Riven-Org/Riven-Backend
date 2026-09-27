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
