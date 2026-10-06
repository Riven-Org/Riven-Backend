"""Projects, changes, verdicts, bugs and the dashboard summary for the signed-in user."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from riven_api.db import get_session
from riven_api.models import User
from riven_api.routers.auth import current_user
from riven_api.schemas import (
    BugFixIn,
    BugOut,
    BugStatus,
    ChangeIn,
    ChangeOut,
    ChangeStatus,
    DashboardOut,
    ProjectIn,
    ProjectOut,
    VerdictIn,
)
from riven_api.services import work

router = APIRouter(prefix="/v1", tags=["work"])

Session = Annotated[AsyncSession, Depends(get_session)]
Me = Annotated[User, Depends(current_user)]


@router.get("/dashboard")
async def dashboard(session: Session, user: Me) -> DashboardOut:
    return await work.dashboard(session, user)


@router.get("/projects")
async def list_projects(session: Session, user: Me) -> list[ProjectOut]:
    return await work.list_projects(session, user)


@router.post("/projects", status_code=status.HTTP_201_CREATED)
async def create_project(body: ProjectIn, session: Session, user: Me) -> ProjectOut:
    return await work.create_project(session, user, body)


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: str, session: Session, user: Me) -> Response:
    await work.delete_project(session, user, project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/changes")
async def list_changes(
    session: Session,
    user: Me,
    project_id: str | None = None,
    status_: Annotated[ChangeStatus | None, Query(alias="status")] = None,
) -> list[ChangeOut]:
    return await work.list_changes(session, user, project_id=project_id, status_=status_)


@router.post("/changes", status_code=status.HTTP_201_CREATED)
async def create_change(body: ChangeIn, session: Session, user: Me) -> ChangeOut:
    return await work.create_change(session, user, body)


@router.post("/changes/{change_id}/verdict")
async def record_verdict(change_id: str, body: VerdictIn, session: Session, user: Me) -> ChangeOut:
    return await work.record_verdict(session, user, change_id, body)


@router.get("/bugs")
async def list_bugs(
    session: Session,
    user: Me,
    status_: Annotated[BugStatus | None, Query(alias="status")] = None,
) -> list[BugOut]:
    return await work.list_bugs(session, user, status_=status_)


@router.post("/bugs/{bug_id}/fix")
async def fix_bug(bug_id: str, body: BugFixIn, session: Session, user: Me) -> BugOut:
    return await work.fix_bug(session, user, bug_id, body)
