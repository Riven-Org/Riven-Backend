"""Seed a demo org with the MVP scenario (ticket S02.1.2).

    uv run python -m riven_db.seed          # uses RIVEN_DATABASE_URL

Loads one repository whose history walks the MVP 15-step scenario: a human change passes; an
AI agent's change fails and a bug is confirmed; a fix is verified and a regression lock is
created; a later AI change trips the lock and the recurrence is detected. The causal graph
links requirement → change → module → bug → fix → test. Running it again changes nothing.
"""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from riven_config import DatabaseSettings
from riven_db.graph_repository import GraphRepository
from riven_db.models import (
    Bug,
    Change,
    RegressionLock,
    Repository,
    VerificationRun,
)
from riven_schemas import (
    BugState,
    LockStatus,
    NodeKind,
    ProducerKind,
    RunState,
    Severity,
    VerificationStage,
    VerificationStatus,
)

DEMO_ORG = "demo"
DEMO_REPO = "riven-demo/shop"
VERIFIER = "riven-verifier"
LOCK_TEST = "tests/test_token_expiry.py::test_token_valid_until_exact_expiry"
T0 = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)


@dataclass(frozen=True)
class DemoChange:
    sha: str
    title: str
    kind: ProducerKind
    identity: str
    files: tuple[str, ...]
    verdict: VerificationStatus
    failed_stage: VerificationStage | None = None
    agent_model: str | None = None


CHANGES = (
    DemoChange(
        "a1b2c3d",
        "Add session tokens",
        ProducerKind.HUMAN,
        "alice@demo.dev",
        ("auth/token.py", "tests/test_token.py"),
        VerificationStatus.PASSED,
    ),
    DemoChange(
        "b2c3d4e",
        "Refactor token expiry",
        ProducerKind.AI_AGENT,
        "agent:claude-code",
        ("auth/token.py",),
        VerificationStatus.FAILED,
        VerificationStage.VERIFY,
        "claude",
    ),
    DemoChange(
        "c3d4e5f",
        "Fix off-by-one in token expiry",
        ProducerKind.HUMAN,
        "bob@demo.dev",
        ("auth/token.py", "tests/test_token_expiry.py"),
        VerificationStatus.PASSED,
    ),
    DemoChange(
        "d4e5f6a",
        "Speed up token refresh",
        ProducerKind.AI_AGENT,
        "agent:claude-code",
        ("auth/token.py",),
        VerificationStatus.FAILED,
        VerificationStage.VERIFY,
        "claude",
    ),
    DemoChange(
        "e5f6a7b",
        "Update checkout copy",
        ProducerKind.BOT,
        "bot:renovate",
        ("web/checkout.html",),
        VerificationStatus.NEEDS_REVIEW,
    ),
)


def _stages(failed: VerificationStage | None) -> list[dict[str, Any]]:
    stages = []
    for stage in list(VerificationStage)[1:]:
        ok = stage is not failed
        stages.append({"stage": stage.value, "ok": ok, "detail": "" if ok else "1 test failed"})
        if not ok:
            break
    return stages


async def seed(session: AsyncSession) -> bool:
    """Insert the demo data; return False if it was already there."""
    existing = await session.scalar(
        select(Repository).where(Repository.org_id == DEMO_ORG, Repository.full_name == DEMO_REPO)
    )
    if existing is not None:
        return False

    repo = Repository(org_id=DEMO_ORG, full_name=DEMO_REPO, provider="github")
    session.add(repo)
    await session.flush()

    changes: dict[str, Change] = {}
    for i, c in enumerate(CHANGES):
        at = T0 + timedelta(days=i)
        change = Change(
            org_id=DEMO_ORG,
            repository_id=repo.id,
            commit_sha=c.sha,
            title=c.title,
            branch="main",
            producer_kind=c.kind.value,
            producer_identity=c.identity,
            agent_model=c.agent_model,
            files_changed=list(c.files),
            captured_at=at,
        )
        session.add(change)
        await session.flush()
        changes[c.sha] = change
        session.add(
            VerificationRun(
                org_id=DEMO_ORG,
                change_id=change.id,
                workflow_id=f"verify:{DEMO_ORG}:{DEMO_REPO}:{c.sha}",
                state=RunState.COMPLETED.value,
                verdict=c.verdict.value,
                verifier_identity=VERIFIER,
                stages=_stages(c.failed_stage),
                started_at=at,
                finished_at=at + timedelta(minutes=4),
            )
        )

    bug = Bug(
        org_id=DEMO_ORG,
        repository_id=repo.id,
        fingerprint="AssertionError:auth/token.py:expiry",
        title="Tokens expire one second early",
        state=BugState.LOCKED.value,
        severity=Severity.HIGH.value,
        module="auth/token.py",
        first_seen_change_id=changes["b2c3d4e"].id,
        occurrences=2,
    )
    session.add(bug)
    await session.flush()
    session.add(
        RegressionLock(
            org_id=DEMO_ORG,
            bug_id=bug.id,
            test_ref=LOCK_TEST,
            fixed_by_change_id=changes["c3d4e5f"].id,
            status=LockStatus.ACTIVE.value,
        )
    )

    graph = GraphRepository(session, DEMO_ORG)
    nodes = {
        name: await graph.upsert_node(kind, key, label)
        for name, kind, key, label in (
            ("req", NodeKind.REQUIREMENT, "REQ-12", "Sessions last exactly 30 minutes"),
            ("change", NodeKind.CHANGE, "b2c3d4e", "Refactor token expiry"),
            ("module", NodeKind.MODULE, "auth/token.py", "auth/token.py"),
            ("bug", NodeKind.BUG, str(bug.id), "Tokens expire one second early"),
            ("fix", NodeKind.FIX, "c3d4e5f", "Fix off-by-one in token expiry"),
            ("test", NodeKind.TEST, LOCK_TEST, "test_token_valid_until_exact_expiry"),
            ("recurrence", NodeKind.CHANGE, "d4e5f6a", "Speed up token refresh"),
        )
    }
    for source, kind, target in (
        ("change", "implements", "req"),
        ("change", "modifies", "module"),
        ("change", "introduced", "bug"),
        ("bug", "located_in", "module"),
        ("fix", "fixes", "bug"),
        ("test", "guards", "bug"),
        ("recurrence", "reintroduced", "bug"),
    ):
        await graph.add_edge(
            nodes[source], kind, nodes[target], provenance="seed", created_by="riven-seed"
        )
    return True


async def main() -> None:
    engine = create_async_engine(DatabaseSettings.load().database_url.get_secret_value())
    async with async_sessionmaker(engine, expire_on_commit=False)() as session, session.begin():
        created = await seed(session)
    await engine.dispose()
    print(f"Seeded demo org '{DEMO_ORG}' ({DEMO_REPO})" if created else "Demo data already present")


if __name__ == "__main__":
    asyncio.run(main())
