"""Submitting and reading changes (S03.4.3). All reads and writes go through row-level
security (TenantSession)."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field

from riven_api.auth.access import PermissionedRoute, Requires
from riven_api.auth.org import OrgContext, TenantSession
from riven_api.auth.permissions import Permission
from riven_api.services import changes
from riven_db.models import Change, Repository
from riven_schemas import ProducerKind

router = APIRouter(prefix="/v1", tags=["changes"], route_class=PermissionedRoute)


class ChangeIn(BaseModel):
    """What was changed. Who changed it comes from the credentials, never from here."""

    model_config = ConfigDict(extra="forbid")

    repository: str = Field(pattern=r"^[\w.-]+/[\w.-]+$", max_length=255)
    commit_sha: str = Field(pattern=r"^[0-9a-fA-F]{7,64}$")
    pr_number: int | None = Field(default=None, ge=1)
    title: str = Field(default="", max_length=500)
    branch: str | None = Field(default=None, max_length=255)
    files_changed: list[str] = Field(default_factory=list, max_length=5000)


class ProducerOut(BaseModel):
    kind: ProducerKind
    identity: str
    agent_model: str | None


class ChangeOut(BaseModel):
    id: UUID
    repository: str
    commit_sha: str
    pr_number: int | None
    title: str
    branch: str | None
    files_changed: list[str]
    producer: ProducerOut = Field(description="The authenticated identity that submitted it")
    captured_at: datetime

    @classmethod
    def of(cls, change: Change, repo: Repository) -> "ChangeOut":
        return cls(
            id=change.id,
            repository=repo.full_name,
            commit_sha=change.commit_sha,
            pr_number=change.pr_number,
            title=change.title,
            branch=change.branch,
            files_changed=list(change.files_changed),
            producer=ProducerOut(
                kind=ProducerKind(change.producer_kind),
                identity=change.producer_identity,
                agent_model=change.agent_model,
            ),
            captured_at=change.captured_at,
        )


@router.post("/orgs/{org_id}/changes", status_code=201)
async def submit_change(
    body: ChangeIn,
    ctx: Annotated[OrgContext, Requires(Permission.CHANGES_SUBMIT)],
    session: TenantSession,
    response: Response,
) -> ChangeOut:
    """Capture a change for verification, attributed to the authenticated caller."""
    captured = await changes.capture(
        session,
        ctx.org_id,
        ctx.principal.producer,
        repository=body.repository,
        commit_sha=body.commit_sha.lower(),
        pr_number=body.pr_number,
        title=body.title,
        branch=body.branch,
        files_changed=body.files_changed,
    )
    await session.commit()
    if not captured.created:
        response.status_code = status.HTTP_200_OK
    return ChangeOut.of(captured.change, captured.repository)


@router.get("/orgs/{org_id}/changes")
async def list_changes(
    _: Annotated[OrgContext, Requires(Permission.CHANGES_READ)], session: TenantSession
) -> list[ChangeOut]:
    return [ChangeOut.of(c, r) for c, r in await changes.list_changes(session)]


@router.get("/orgs/{org_id}/changes/{change_id}")
async def get_change(
    change_id: UUID,
    _: Annotated[OrgContext, Requires(Permission.CHANGES_READ)],
    session: TenantSession,
) -> ChangeOut:
    found = await changes.get_change(session, change_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="change_not_found")
    return ChangeOut.of(*found)
