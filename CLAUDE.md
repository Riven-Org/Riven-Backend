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

**Reset to a minimal app (ADR 0014, branch `RESET-minimal-auth`).** The API is one FastAPI service on SQLite with email + password sign-up/login and JWT bearer tokens. Everything else (Keycloak, Postgres/RLS, orgs/roles/API keys, Temporal worker, events, object storage, shared schemas, Docker) was removed and lives in git history; tickets that depend on it must bring the needed piece back first. The dashboard lives in [Riven-Frontend](https://github.com/Riven-Org/Riven-Frontend).

## Commands

Run from the repo root (settings read `.env` from the working directory).

```bash
uv sync                                  # install
make check                               # = CI: ruff check, ruff format --check, mypy --strict, pytest
uv run pytest apps/api/tests/test_auth.py::test_me_needs_a_valid_token   # single test
make fmt                                 # auto-fix lint + format
make api                                 # :8000, OpenAPI docs at /docs; creates ./riven.db on start
```

## Architecture and conventions

- `apps/api/src/riven_api`: `create_app()` factory; `config.py` (`Settings`, env prefix `RIVEN_`, never read `os.environ` directly); `db.py` (`Base`, async engine, `get_session` dependency; tables created in the app lifespan); `models.py` (SQLAlchemy 2.0 typed models); `security.py` (Argon2 hashing, JWT create/read); `routers/` (thin HTTP layer, mounted under `/v1`, health unversioned).
- Endpoints needing a signed-in user depend on `current_user` from `routers/auth.py`.
- Tests use the `client` fixture in `apps/api/tests/conftest.py` (fresh SQLite file per test, lifespan run by `TestClient`).
- mypy strict covers `apps/api/src`; ruff treats `riven_api` as first-party.
- New significant decisions get a new numbered ADR in `docs/adr/`.

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
