"""Change capture with the authenticated producer (S03.4.3).

The producer is always derived from who authenticated the request (a person, or a service
account acting for an AI agent, CI or bot), never from the request body, so a change can't
claim to come from someone else. That identity is what later lets Riven refuse to let a
producer verify its own change.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from riven_db.models import Change, Repository
from riven_events import add_event
from riven_schemas import ChangeCaptured, ChangeRef, Producer


@dataclass(frozen=True)
class CapturedChange:
    change: Change
    repository: Repository
    created: bool


async def capture(
    session: AsyncSession,
    org_id: str,
    producer: Producer,
    *,
    repository: str,
    commit_sha: str,
    pr_number: int | None,
    title: str,
    branch: str | None,
    files_changed: list[str],
) -> CapturedChange:
    """Record a change (idempotent per repository + commit) and publish change.captured."""
    repo = await session.scalar(select(Repository).where(Repository.full_name == repository))
    if repo is None:
        repo = Repository(org_id=org_id, full_name=repository)
        session.add(repo)
        await session.flush()
    existing = await session.scalar(
        select(Change).where(Change.repository_id == repo.id, Change.commit_sha == commit_sha)
    )
    if existing is not None:
        return CapturedChange(existing, repo, created=False)
    change = Change(
        org_id=org_id,
        repository_id=repo.id,
        commit_sha=commit_sha,
        pr_number=pr_number,
        title=title,
        branch=branch,
        producer_kind=producer.kind.value,
        producer_identity=producer.identity,
        agent_model=producer.agent_model,
        files_changed=files_changed,
    )
    session.add(change)
    await session.flush()
    add_event(
        session,
        ChangeCaptured(
            change=ChangeRef(
                org_id=org_id, repo=repository, commit_sha=commit_sha, pr_number=pr_number
            ),
            producer=producer,
            files_changed=files_changed,
        ),
        org_id=org_id,
    )
    return CapturedChange(change, repo, created=True)


async def list_changes(session: AsyncSession, limit: int = 50) -> list[tuple[Change, Repository]]:
    rows = await session.execute(
        select(Change, Repository)
        .join(Repository, Repository.id == Change.repository_id)
        .order_by(Change.captured_at.desc())
        .limit(limit)
    )
    return [(c, r) for c, r in rows.all()]


async def get_change(session: AsyncSession, change_id: UUID) -> tuple[Change, Repository] | None:
    row = (
        await session.execute(
            select(Change, Repository)
            .join(Repository, Repository.id == Change.repository_id)
            .where(Change.id == change_id)
        )
    ).first()
    return (row[0], row[1]) if row else None
