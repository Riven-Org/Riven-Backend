"""Projects, changes, verdicts and bugs. Every function is scoped to one owner."""

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from riven_api.models import Bug, Change, Project, User
from riven_api.schemas import (
    ActivityItem,
    BugFixIn,
    BugOut,
    ChangeIn,
    ChangeOut,
    DashboardOut,
    Kpi,
    Kpis,
    ProjectIn,
    ProjectOut,
    Totals,
    TrendDay,
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


# ---------------------------------------------------------------- numbering


async def _numbers(
    session: AsyncSession, user: User, model: type[Change] | type[Bug]
) -> dict[str, int]:
    """Per-user sequence numbers (#1, #2, …) by creation order, without storing them."""
    n = func.row_number().over(order_by=(model.created_at, model.id))
    rows = await session.execute(select(model.id, n).where(model.owner_id == user.id))
    return dict(rows.tuples().all())


# ---------------------------------------------------------------- changes


def _change_out(change: Change, project_name: str, user: User, number: int = 0) -> ChangeOut:
    return ChangeOut(
        id=change.id,
        number=number,
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
    numbers = await _numbers(session, user, Change)
    return [
        _change_out(c, names.get(c.project_id, ""), user, numbers.get(c.id, 0)) for c in changes
    ]


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
    return (await _changes_out(session, user, [change]))[0]


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
    return (await _changes_out(session, user, [change]))[0]


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
    numbers = await _numbers(session, user, Bug)
    return [
        BugOut(
            id=b.id,
            number=numbers.get(b.id, 0),
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
    session: AsyncSession,
    user: User,
    *,
    project_id: str | None = None,
    status_: str | None = None,
    limit: int = 200,
) -> list[BugOut]:
    query = select(Bug).where(Bug.owner_id == user.id)
    if project_id:
        query = query.where(Bug.project_id == project_id)
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


def _day(value: datetime) -> date:
    return _utc(value).date()


def _kpi(per_day: dict[date, int], days: list[date], previous: int) -> Kpi:
    return Kpi(
        value=sum(per_day.get(d, 0) for d in days),
        previous=previous,
        series=[per_day.get(d, 0) for d in days],
    )


async def dashboard(
    session: AsyncSession,
    user: User,
    *,
    days: int = 7,
    project_id: str | None = None,
    today: date | None = None,
) -> DashboardOut:
    if project_id:
        await get_project(session, user, project_id)
    today = today or datetime.now(UTC).date()
    period = [today - timedelta(days=days - 1 - i) for i in range(days)]
    start = period[0]
    prev_start = start - timedelta(days=days)

    change_q = select(Change).where(Change.owner_id == user.id)
    bug_q = select(Bug).where(Bug.owner_id == user.id)
    if project_id:
        change_q = change_q.where(Change.project_id == project_id)
        bug_q = bug_q.where(Bug.project_id == project_id)
    changes = (await session.scalars(change_q)).all()
    bugs = (await session.scalars(bug_q)).all()

    logged: dict[date, int] = {}
    judged: dict[date, int] = {}
    verdicts: dict[tuple[date, str], int] = {}
    prev_logged = prev_judged = 0
    for c in changes:
        d = _day(c.created_at)
        logged[d] = logged.get(d, 0) + 1
        prev_logged += prev_start <= d < start
        if c.verified_at:
            v = _day(c.verified_at)
            judged[v] = judged.get(v, 0) + 1
            verdicts[(v, c.status)] = verdicts.get((v, c.status), 0) + 1
            prev_judged += prev_start <= v < start
    found: dict[date, int] = {}
    prev_found = 0
    for b in bugs:
        d = _day(b.created_at)
        found[d] = found.get(d, 0) + 1
        prev_found += prev_start <= d < start
    remembered = [sum(1 for b in bugs if _day(b.created_at) <= d) for d in period]
    before = sum(1 for b in bugs if _day(b.created_at) < start)

    status_counts = {
        k: sum(1 for c in changes if c.status == k)
        for k in ("pending", "passed", "failed", "needs_review")
    }
    passed, failed = status_counts["passed"], status_counts["failed"]
    projects = await session.scalar(
        select(func.count()).select_from(Project).where(Project.owner_id == user.id)
    )
    newest = sorted(changes, key=lambda c: _utc(c.created_at), reverse=True)
    judged_newest = sorted(
        (c for c in changes if c.verified_at),
        key=lambda c: _utc(c.verified_at or c.created_at),
        reverse=True,
    )
    bugs_newest = sorted(bugs, key=lambda b: _utc(b.created_at), reverse=True)

    return DashboardOut(
        days=days,
        project_id=project_id,
        totals=Totals(
            projects=projects or 0,
            changes=len(changes),
            pending=status_counts["pending"],
            passed=passed,
            failed=failed,
            needs_review=status_counts["needs_review"],
            open_bugs=sum(1 for b in bugs if b.status == "open"),
            fixed_bugs=sum(1 for b in bugs if b.status == "fixed"),
        ),
        kpis=Kpis(
            changes=_kpi(logged, period, prev_logged),
            verified=_kpi(judged, period, prev_judged),
            bugs=_kpi(found, period, prev_found),
            memories=Kpi(value=len(bugs), previous=before, series=remembered),
        ),
        pass_rate=passed / (passed + failed) if passed + failed else None,
        by_producer={
            k: sum(1 for c in changes if c.producer == k) for k in ("human", "ai_agent", "bot")
        },
        trend=[
            TrendDay(
                day=d,
                logged=logged.get(d, 0),
                passed=verdicts.get((d, "passed"), 0),
                failed=verdicts.get((d, "failed"), 0),
                needs_review=verdicts.get((d, "needs_review"), 0),
            )
            for d in period
        ],
        recent=await _changes_out(session, user, newest[:6]),
        active=await _changes_out(
            session, user, [c for c in newest if c.status in ("pending", "needs_review")][:8]
        ),
        runs=await _changes_out(session, user, judged_newest[:6]),
        open_bugs=await _bugs_out(
            session, user, [b for b in bugs_newest if b.status == "open"][:5]
        ),
        chains=await _bugs_out(session, user, bugs_newest[:4]),
    )


# ---------------------------------------------------------------- activity


async def activity(
    session: AsyncSession, user: User, *, project_id: str | None = None, limit: int = 20
) -> list[ActivityItem]:
    """What happened recently, derived from timestamps on changes and bugs."""
    changes = await list_changes(session, user, project_id=project_id, limit=limit)
    bugs = await list_bugs(session, user, project_id=project_id, limit=limit)
    items: list[ActivityItem] = []
    for c in changes:
        items.append(
            ActivityItem(
                kind="change_logged",
                at=c.created_at,
                number=c.number,
                title=c.title,
                detail=f"Logged by {c.author or c.producer.replace('_', ' ')}",
                project_name=c.project_name,
                status="pending",
            )
        )
        if c.verified_at:
            items.append(
                ActivityItem(
                    kind="verdict",
                    at=c.verified_at,
                    number=c.number,
                    title=c.title,
                    detail={
                        "passed": "Verified successfully",
                        "failed": "Failed verification",
                        "needs_review": "Flagged for review",
                    }.get(c.status, c.status),
                    project_name=c.project_name,
                    status=c.status,
                )
            )
    for b in bugs:
        items.append(
            ActivityItem(
                kind="bug_found",
                at=b.created_at,
                number=b.number,
                title=b.title,
                detail=f"Remembered from {b.change_commit[:7]}",
                project_name=b.project_name,
                status="open",
            )
        )
        if b.fixed_at:
            items.append(
                ActivityItem(
                    kind="bug_fixed",
                    at=b.fixed_at,
                    number=b.number,
                    title=b.title,
                    detail=f"Fixed by {b.fixed_by_commit[:7]}" if b.fixed_by_commit else "Fixed",
                    project_name=b.project_name,
                    status="fixed",
                )
            )
    items.sort(key=lambda i: i.at, reverse=True)
    return items[:limit]
