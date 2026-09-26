# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Product

Riven is an independent verification and institutional-memory layer for AI-built software. It sits between a code change and its acceptance: it captures the change, runs it in an isolated sandbox, verifies it independently, remembers confirmed bugs, turns them into regression locks, and links requirement → change → module → bug → fix → test in a causal graph.

**Core principle: Riven never approves its own work.** Whoever produced a change (human, AI agent, or Riven itself) must never be the identity that verifies it. Treat any code path that lets producer identity equal verifier identity as a bug.

Pipeline: capture → analyze → sandbox → verify → (bug detection ∥ regression check) → memory → causal graph → dashboard. Learning loop: detect → understand → remember → verify → protect.

Domain terms used across tickets and code:

| Term | Meaning |
|---|---|
| Change | A commit or PR in a customer repo (`ChangeRef`: org, repo, commit, PR) |
| Producer | Who made the change: `human`, `ai_agent`, `bot`, `unknown` |
| Verdict | `passed`, `failed`, `needs_review` for one verification run |
| Finding | One problem reported by a verifier plugin, with severity and confidence |
| Fingerprint | Normalized error signature used to recognise the same bug across runs |
| Regression lock | A test that fails on the buggy commit and passes on the fix; re-run on related changes |
| Causal graph | Nodes (requirement, change, module, symbol, bug, fix, test, decision, …) and edges with provenance, stored in Postgres |

## Current state

Only the foundation scaffold exists: health endpoints, settings, DB session, the pipeline workflow with **placeholder activities**, shared schemas. The FYP MVP described as "Baseline B01–B08" in `docs/tickets/INDEX.md` is **specified but not implemented**. When a ticket says "port the MVP X" or "MVP scenario still passes", build X fresh to the spec and treat the MVP 15-step scenario (change → capture → sandbox → verify → bug found → stored → fixed → fix verified → lock created → later change → lock re-run → recurrence detected → graph shows links → dashboard shows history) as the target behaviour.

The dashboard lives in [Riven-Frontend](https://github.com/Riven-Org/Riven-Frontend).

## Commands

Run from the repo root (settings read `.env` from the working directory).

```bash
uv sync                                  # install workspace
make check                               # = CI: ruff check, ruff format --check, mypy --strict, pytest
uv run pytest apps/api/tests/test_health.py::test_health_returns_ok    # single test
uv run pytest -k workflow                # by keyword
make fmt                                 # auto-fix lint + format
make dev                                 # whole stack in Docker + migrations + demo seed (CI job `stack` runs it)
make up && make migrate                  # infra only (Postgres(pgvector)/Redis/MinIO/Temporal), then Alembic
make seed                                # demo org `demo` / repo `riven-demo/shop` (idempotent)
make api                                 # :8000, OpenAPI docs at /docs
make worker                              # Temporal worker, task queue "verification"
uv run alembic -c apps/api/alembic.ini revision --autogenerate -m "<ID>: <what>"
```

Docker is not installed on the maintainer's machine; `make up`/`make dev` may be unavailable locally. Anything needing Postgres/Temporal must also work in CI: the `python` job has Postgres (pgvector) and Redis service containers, and the `stack` job runs `make dev` and checks every container is healthy. New services go in `docker-compose.yml` (one `Dockerfile` image serves every Python service).

## Architecture and conventions

Decisions and reasons: `docs/adr/` (0001 stack, 0002 service decomposition and data ownership, 0003–0010 one per service, 0011 shared persistence package and object storage). New significant decisions get a new numbered ADR in the same PR.

**Workspace** (uv): `apps/api` (`riven_api`), `apps/worker` (`riven_worker`), `packages/schemas` (`riven_schemas`), `packages/events` (`riven_events`), `packages/db` (`riven_db`), `packages/storage` (`riven_storage`). mypy strict covers every `src/` tree; ruff treats the packages as first-party.

**Events** (`riven_events`, S01.3) — publish a domain event with `add_event(session, event, org_id=...)` inside the same transaction as the state change; never write to Redis directly. `make relay` runs the outbox relay (→ Redis Stream `riven:events`). Consume with `EventConsumer(name, sessions, redis, {"<type>": handler})`: the handler runs in the transaction that records the event as processed, so do all side effects through that session. New events: add to `EVENTS` and `catalog.ROUTES`, then `make catalog` (the catalog test fails otherwise). Catalog: `docs/events.md`.

**`packages/schemas`** — every payload that crosses a service boundary (API ↔ worker, events, Temporal inputs/outputs). Never define such a model inside one app. Events subclass `DomainEvent` with a `type: Literal["noun.verb"]`. Register every contract in `contracts.py`; `test_contracts.py` compares it with the committed baseline in `packages/schemas/contracts/v<SCHEMA_VERSION>/`. Additive changes pass; a breaking change fails CI until you bump `SCHEMA_VERSION` and write a new baseline (`uv run python -m riven_schemas.export --snapshot`). Service boundaries and table ownership: ADRs 0002–0010.

**`apps/api`** — build new features in this shape:
- `routers/<resource>.py`: thin HTTP layer, mounted under `/v1` (health stays unversioned). Declare the required permission on every mutating endpoint once RBAC (S03.3) exists.
- `services/<area>.py`: business logic; routers call services, services take an `AsyncSession`.
- Models: SQLAlchemy 2.0 typed models live in `packages/db` (`riven_db.models.<owning service>`, ADR 0011) because worker services own tables too. Every domain table uses `TenantMixin` (non-null indexed `org_id`); queries are always org-scoped. Export new model modules from `riven_db/models/__init__.py` so autogenerate and the drift test see them.
- Every schema change is an Alembic migration named `<ID>: …`; never edit an applied migration. `packages/db/tests/test_migrations.py` fails when models and migrations drift.
- Logs and artifacts go to object storage through `riven_storage.ObjectStore` (MinIO locally, S3 in the cloud), downloaded via presigned URLs; services never write to local disk (a test enforces it).
- Tests use `create_app()` + `app.dependency_overrides[get_session]`; no test may require a live external service unless CI provides it. CI provides Postgres (pgvector) and Redis: tests using the root `conftest.py` fixtures (`sessions`, `db_engine`, `redis`) run against a migrated database when `RIVEN_TEST_DATABASE_URL` is set and are skipped otherwise; `redis` falls back to fakeredis.

**`apps/worker`** — pipeline logic lives in activities; `VerificationWorkflow` only orchestrates. Workflow code must stay deterministic (no I/O, clock, randomness; imports of app code inside `workflow.unsafe.imports_passed_through()`). Register new activities in `ALL_ACTIVITIES` with an explicit timeout and `STAGE_RETRY`. Client and worker must both use `pydantic_data_converter`. `workflow_id_for()` is the idempotency key per (org, repo, commit) — keep it stable.

**Causal graph** — Postgres tables (`graph_nodes`, `graph_edges`), not a graph database. Every edge carries provenance: source, confidence, created_by, and valid_from/valid_to (close edges, never delete). Traversals use recursive CTEs through one org-scoped repository module.

**LLM calls** — go through a single gateway module (built in S11.3: budgets, caching, secret redaction). Features never call a provider SDK directly. Default provider is the Claude API; secrets and customer code must be redacted before any call.

**Sandbox** — runs untrusted customer and AI-generated code. Deny network egress by default, cap CPU/memory/time, and classify infrastructure failures (timeout, OOM) separately from code failures — infra failures never create bugs.

**Infra tickets** (Terraform, Helm, Kubernetes, Argo) live under `infra/` in this repo until a dedicated repo exists.

**Cost** — the org is on free plans (GitHub Free, ClickUp Free Forever). Choose self-hosted/open-source options; never add a paid service, licensed GitHub Action, or larger runner. If a ticket's suggested tech is paid, use the free alternative and say so in the PR.

## Guardrails (enforced)

`.claude/hooks/guard.py` runs before every shell command and file edit and blocks: force push (`-f`, `--force`, `--force-with-lease`, `+refspec`), pushing to or deleting `main`, `--no-verify`, `git reset --hard`, `gh pr merge --admin`, opening pull requests (`gh pr create` — the user opens PRs), changing repo visibility, deleting/archiving repos, Codespaces, changing branch protection or rulesets, editing `docs/tickets/`, and in workflows any licensed action (e.g. `gitleaks/gitleaks-action`) or non-standard (paid, larger) runner. `.claude/settings.json` also denies reading `.env` and always asks the user before `git push` and `gh pr merge`. If a guard blocks something the task genuinely needs, stop and ask the user; never work around it.

The guard matches the whole command text, so a commit message or heredoc that merely mentions a blocked flag is also blocked; put such text in a file (`git commit -F <file>`).

## Implementing a ticket

Ticket details live in `docs/tickets/`: `INDEX.md` lists every epic and story; `<story-id>.md` holds its description, acceptance criteria, dependencies, tech notes and tasks. A task ID like `S01.2.3` is inside `S01.2.md`. Each task is labelled **Repo: backend / frontend / both**.

When asked to do a ticket (e.g. "do S07.4" or "S01.2.3"):

1. **Read** the story file, the epic context at its end, and any ADRs it touches. For an epic ID, work story by story in the order listed, one PR per story.
2. **Check the repo label.** Implement only tasks labelled `backend` or `both` (backend half). If nothing is for this repo, stop and say it belongs to Riven-Frontend.
3. **Check dependencies** listed on the story and task: `gh pr list -R Riven-Org/Riven-Backend --state merged --search "<DEP-ID>"` (and the frontend repo for UI deps), plus a look at the code. If a dependency is missing, stop and report it; do not quietly build dependency work inside this ticket unless the user says to.
4. **Plan** by mapping every acceptance criterion (story + in-scope tasks) to the code that satisfies it and the test that proves it. The task "What to do" lines are terse — fill gaps with the story description, epic context and conventions above, never by expanding scope.
5. **Branch** — every ticket starts from the latest main on a new branch: `git switch main && git pull --ff-only origin main && git switch -c <ID>-<short-slug>`. Never commit on main or reuse another ticket's branch.
6. **Implement** only what the acceptance criteria require. Out-of-scope needs you discover go in the PR's follow-ups, with the ticket ID they belong to if one exists in `INDEX.md`.
7. **Test**: at least one test per acceptance criterion, named after the behaviour. Performance criteria (e.g. "< 300 ms p95") get a measurement, not an assumption. Run `make check`; for runtime behaviour also start the service and exercise it.
8. **Commit** as `<ID>: <summary>`.
9. **Sync with main before every push**: `git fetch origin && git merge origin/main`. Resolve any conflicts by keeping both sides' intent (never drop the other change to make yours apply), re-run `make check`, and commit the merge. Use merge, not rebase, once the branch is pushed — rewriting pushed history would need a force push, which is blocked.
10. **Push** the branch: `git push -u origin <branch>`. **Do not open a pull request** — the user opens it. CI runs on every branch push; watch it with `gh run watch $(gh run list --branch <branch> -L1 --json databaseId -q '.[0].databaseId')` and fix until green.
11. **Report**: branch name, compare link `https://github.com/Riven-Org/Riven-Backend/compare/main...<branch>?expand=1`, a ready-to-paste PR description (ticket ID, acceptance-criteria checklist ticked only if proven, how it was tested, follow-ups including the frontend half of `both` tasks), which criteria are met or not and why (e.g. needs cloud, staging or Docker), and a reminder to move the ClickUp ticket. Never merge.

Ticket files are generated from the product backlog (also in ClickUp). Do not edit them by hand; if a ticket looks wrong or contradicts an ADR, say so and ask.
