# ADR 0012: Configuration, secrets and environments

- **Status:** Accepted
- **Date:** 2026-09-27
- **Ticket:** S02.2

## Context

Every service needs database, Redis, Temporal and storage settings. Mistakes (a typo in an
environment name, a dev password in production) should stop a service at startup, not surface
as a failure hours later. Secrets must stay out of git, and rotating one must not need a code
change. The org is on free plans, so a paid secrets manager is not an option today.

## Decision

- **Typed settings, one package.** `packages/config` (`riven_config`) provides `RivenSettings`
  and building blocks (`DatabaseSettings`, `RedisSettings`, `TemporalSettings`,
  `StorageSettings`). Each service composes the blocks it needs and calls `.load()` at
  startup; invalid configuration exits with status 1 and a list of the problems.
- **Environments:** `RIVEN_ENV` is one of `dev`, `test`, `staging`, `prod`. In `staging` and
  `prod`, any setting containing a development credential (the values used by
  `docker-compose.yml` and `.env.example`) is rejected, and CORS origins must be `https://`.
- **Secrets are `SecretStr`** (hidden in reprs, logs and dumps) and are read, in order of
  precedence, from environment variables, then files in `RIVEN_SECRETS_DIR` (one file per
  setting, named like the variable in lower case, e.g. `riven_database_url`), then `.env`.
  The file form is what Docker secrets and the Kubernetes Secrets Store CSI driver mount, so
  any backing store (Kubernetes Secrets, HashiCorp Vault, or a cloud secrets manager later)
  plugs in without code changes. Rotation = update the secret, restart the pods.
- **No secrets in git:** gitleaks runs in CI (`secrets` job) and as a pre-commit hook.
- **Separate staging and prod accounts:** each environment gets its own cloud account or
  project with no cross-environment IAM. This is provisioned with the infrastructure baseline
  (S02.4); no cloud account exists yet.

## Consequences

- Adding a setting means adding a typed field to the relevant block; tests cover validation.
- Paid secrets managers are optional future backends behind the same file interface.
