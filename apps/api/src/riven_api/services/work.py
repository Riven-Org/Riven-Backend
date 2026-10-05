"""Projects, changes, verdicts and bugs. Every function is scoped to one owner."""

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from riven_api.models import Bug, Change, Project, User
from riven_api.schemas import (
    BugFixIn,
    BugOut,
    ChangeIn,
    ChangeOut,
    DashboardOut,
    DayCount,
    ProjectIn,
    ProjectOut,
    Totals,
    VerdictIn,
)

SELF_APPROVAL = (
    "Riven never approves its own work: you produced this change, so you can't judge it."
)


def _not_found(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")


def _utc(value: datetime) -> datetime:
    # SQLite returns naive datetimes; everything is stored in UTC.
    return value if value.tzinfo else value.replace(tzinfo=UTC)


# ---------------------------------------------------------------- projects


async def list_projects(session: AsyncSession, user: User) -> list[ProjectOut]:
    projects = (
        await session.scalars(
            select(Project).where(Project.owner_id == user.id).order_by(Project.created_at)
        )
    ).all()
    changes = dict(
        (
            await session.execute(
                select(Change.project_id, func.count())
                .where(Change.owner_id == user.id)
                .group_by(Change.project_id)
            )
        )
        .tuples()
        .all()
    )
    bugs = dict(
        (
            await session.execute(
                select(Bug.project_id, func.count())
                .where(Bug.owner_id == user.id, Bug.status == "open")
                .group_by(Bug.project_id)
            )
        )
        .tuples()
        .all()
    )
    return [
        ProjectOut.model_validate(p).model_copy(
            update={"changes": changes.get(p.id, 0), "open_bugs": bugs.get(p.id, 0)}
        )
        for p in projects
    ]


async def get_project(session: AsyncSession, user: User, project_id: str) -> Project:
    project = await session.get(Project, project_id)
    if project is None or project.owner_id != user.id:
        raise _not_found("Project")
    return project


async def create_project(session: AsyncSession, user: User, body: ProjectIn) -> ProjectOut:
    name = body.name.strip()
    taken = await session.scalar(
        select(Project.id).where(
            Project.owner_id == user.id, func.lower(Project.name) == name.lower()
        )
    )
    if taken:
        raise HTTPException(status.HTTP_409_CONFLICT, "You already have a project with this name")
    project = Project(
        owner_id=user.id,
        name=name,
        repo_url=body.repo_url.strip(),
        description=body.description.strip(),
    )
    session.add(project)
    await session.commit()
    return ProjectOut.model_validate(project)


async def delete_project(session: AsyncSession, user: User, project_id: str) -> None:
    project = await get_project(session, user, project_id)
    # SQLite doesn't enforce foreign keys by default, so remove dependents explicitly.
    await session.execute(delete(Bug).where(Bug.project_id == project.id))
    await session.execute(delete(Change).where(Change.project_id == project.id))
    await session.delete(project)
    await session.commit()


# ---------------------------------------------------------------- changes


def _change_out(change: Change, project_name: str, user: User) -> ChangeOut:
    return ChangeOut(
        id=change.id,
        project_id=change.project_id,
        project_name=project_name,
        commit=change.commit,
        title=change.title,
        producer=change.producer,
        author=change.author,
        status=change.status,
        note=change.note,
        created_at=_utc(change.created_at),
        verified_at=_utc(change.verified_at) if change.verified_at else None,
        self_produced=_self_produced(change, user),
    )


def _self_produced(change: Change, user: User) -> bool:
    """A human change logged by this user was produced by this user."""
    return change.producer == "human" and change.created_by == user.id


async def _changes_out(
    session: AsyncSession, user: User, changes: Sequence[Change]
) -> list[ChangeOut]:
    names = dict(
        (await session.execute(select(Project.id, Project.name).where(Project.owner_id == user.id)))
        .tuples()
        .all()
    )
    return [_change_out(c, names.get(c.project_id, ""), user) for c in changes]


async def list_changes(
    session: AsyncSession,
    user: User,
    *,
    project_id: str | None = None,
    status_: str | None = None,
    limit: int = 200,
) -> list[ChangeOut]:
    query = select(Change).where(Change.owner_id == user.id)
    if project_id:
        query = query.where(Change.project_id == project_id)
    if status_:
        query = query.where(Change.status == status_)
    rows = (await session.scalars(query.order_by(Change.created_at.desc()).limit(limit))).all()
    return await _changes_out(session, user, rows)


async def create_change(session: AsyncSession, user: User, body: ChangeIn) -> ChangeOut:
    project = await get_project(session, user, body.project_id)
    change = Change(
        owner_id=user.id,
        project_id=project.id,
        commit=body.commit.lower(),
        title=body.title.strip(),
        producer=body.producer,
        author=body.author.strip() or (user.name if body.producer == "human" else ""),
        created_by=user.id,
    )
    session.add(change)
    await session.commit()
    return _change_out(change, project.name, user)


async def _get_change(session: AsyncSession, user: User, change_id: str) -> Change:
    change = await session.get(Change, change_id)
    if change is None or change.owner_id != user.id:
        raise _not_found("Change")
    return change


async def record_verdict(
    session: AsyncSession, user: User, change_id: str, body: VerdictIn
) -> ChangeOut:
    change = await _get_change(session, user, change_id)
    if _self_produced(change, user):
        raise HTTPException(status.HTTP_409_CONFLICT, SELF_APPROVAL)
    if change.status in ("passed", "failed"):
        raise HTTPException(status.HTTP_409_CONFLICT, f"This change already {change.status}")
    if body.verdict == "failed" and not (body.bug_title and body.bug_title.strip()):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Describe the bug that made this change fail"
        )
    change.status = body.verdict
    change.note = body.note.strip()
    change.verified_by = user.id
    change.verified_at = datetime.now(UTC)
    if body.verdict == "failed" and body.bug_title:
        session.add(
            Bug(
                owner_id=user.id,
                project_id=change.project_id,
                change_id=change.id,
                title=body.bug_title.strip(),
                severity=body.bug_severity,
            )
        )
    await session.commit()
    project = await session.get(Project, change.project_id)
    return _change_out(change, project.name if project else "", user)


# ---------------------------------------------------------------- bugs


async def _bugs_out(session: AsyncSession, user: User, bugs: Sequence[Bug]) -> list[BugOut]:
    names = dict(
        (await session.execute(select(Project.id, Project.name).where(Project.owner_id == user.id)))
        .tuples()
        .all()
    )
    ids = {b.change_id for b in bugs} | {b.fixed_by_change_id for b in bugs if b.fixed_by_change_id}
    rows = await session.execute(select(Change.id, Change.commit).where(Change.id.in_(ids)))
    commits = dict(rows.tuples().all())
    return [
        BugOut(
            id=b.id,
            project_id=b.project_id,
            project_name=names.get(b.project_id, ""),
            change_id=b.change_id,
            change_commit=commits.get(b.change_id, ""),
            title=b.title,
            severity=b.severity,
            status=b.status,
            created_at=_utc(b.created_at),
            fixed_at=_utc(b.fixed_at) if b.fixed_at else None,
            fixed_by_commit=commits.get(b.fixed_by_change_id) if b.fixed_by_change_id else None,
        )
        for b in bugs
    ]


async def list_bugs(
    session: AsyncSession, user: User, *, status_: str | None = None, limit: int = 200
) -> list[BugOut]:
    query = select(Bug).where(Bug.owner_id == user.id)
    if status_:
        query = query.where(Bug.status == status_)
    rows = (await session.scalars(query.order_by(Bug.created_at.desc()).limit(limit))).all()
    return await _bugs_out(session, user, rows)


async def fix_bug(session: AsyncSession, user: User, bug_id: str, body: BugFixIn) -> BugOut:
    bug = await session.get(Bug, bug_id)
    if bug is None or bug.owner_id != user.id:
        raise _not_found("Bug")
    if bug.status == "fixed":
        raise HTTPException(status.HTTP_409_CONFLICT, "This bug is already fixed")
    if body.change_id:
        fix = await _get_change(session, user, body.change_id)
        if fix.project_id != bug.project_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "The fix must be a change in the same project",
            )
        if fix.status != "passed":
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Only a change that passed can fix a bug"
            )
        bug.fixed_by_change_id = fix.id
    bug.status = "fixed"
    bug.fixed_at = datetime.now(UTC)
    await session.commit()
    return (await _bugs_out(session, user, [bug]))[0]


# ---------------------------------------------------------------- dashboard

DAYS = 14


async def dashboard(session: AsyncSession, user: User, today: date | None = None) -> DashboardOut:
    today = today or datetime.now(UTC).date()
    since = datetime.combine(today - timedelta(days=DAYS - 1), datetime.min.time(), UTC)

    statuses = dict(
        (
            await session.execute(
                select(Change.status, func.count())
                .where(Change.owner_id == user.id)
                .group_by(Change.status)
            )
        )
        .tuples()
        .all()
    )
    producers = dict(
        (
            await session.execute(
                select(Change.producer, func.count())
                .where(Change.owner_id == user.id)
                .group_by(Change.producer)
            )
        )
        .tuples()
        .all()
    )
    bugs = dict(
        (
            await session.execute(
                select(Bug.status, func.count()).where(Bug.owner_id == user.id).group_by(Bug.status)
            )
        )
        .tuples()
        .all()
    )
    projects = await session.scalar(
        select(func.count()).select_from(Project).where(Project.owner_id == user.id)
    )

    logged: dict[date, int] = {}
    verified: dict[date, int] = {}
    rows = await session.execute(
        select(Change.created_at, Change.verified_at).where(
            Change.owner_id == user.id, Change.created_at >= since.replace(tzinfo=None)
        )
    )
    for created_at, verified_at in rows.tuples():
        logged[_utc(created_at).date()] = logged.get(_utc(created_at).date(), 0) + 1
        if verified_at:
            verified[_utc(verified_at).date()] = verified.get(_utc(verified_at).date(), 0) + 1
    days = [today - timedelta(days=DAYS - 1 - i) for i in range(DAYS)]

    passed, failed = statuses.get("passed", 0), statuses.get("failed", 0)
    return DashboardOut(
        totals=Totals(
            projects=projects or 0,
            changes=sum(statuses.values()),
            pending=statuses.get("pending", 0),
            passed=passed,
            failed=failed,
            needs_review=statuses.get("needs_review", 0),
            open_bugs=bugs.get("open", 0),
            fixed_bugs=bugs.get("fixed", 0),
        ),
        pass_rate=passed / (passed + failed) if passed + failed else None,
        by_producer={k: producers.get(k, 0) for k in ("human", "ai_agent", "bot")},
        daily=[DayCount(day=d, logged=logged.get(d, 0), verified=verified.get(d, 0)) for d in days],
        recent=await list_changes(session, user, limit=6),
        open_bugs=await list_bugs(session, user, status_="open", limit=5),
    )
