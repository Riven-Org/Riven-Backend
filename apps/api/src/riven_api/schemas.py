"""Request and response bodies for the /v1 API."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ProducerKind = Literal["human", "ai_agent", "bot"]
Verdict = Literal["passed", "failed", "needs_review"]
ChangeStatus = Literal["pending", "passed", "failed", "needs_review"]
Severity = Literal["low", "medium", "high", "critical"]
BugStatus = Literal["open", "fixed"]


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    repo_url: str = Field(default="", max_length=300)
    description: str = Field(default="", max_length=500)


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    repo_url: str
    description: str
    created_at: datetime
    changes: int = 0
    open_bugs: int = 0


class ChangeIn(BaseModel):
    project_id: str
    commit: str = Field(min_length=4, max_length=40, pattern=r"^[0-9a-fA-F]+$")
    title: str = Field(min_length=1, max_length=200)
    producer: ProducerKind
    author: str = Field(default="", max_length=120)


class ChangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    # Per-user sequence number, shown as "#24".
    number: int = 0
    project_id: str
    project_name: str
    commit: str
    title: str
    producer: ProducerKind
    author: str
    status: ChangeStatus
    note: str
    created_at: datetime
    verified_at: datetime | None
    # True when the caller produced this change and so may not judge it.
    self_produced: bool


class VerdictIn(BaseModel):
    verdict: Verdict
    note: str = Field(default="", max_length=1000)
    # Record a bug with a failed verdict.
    bug_title: str | None = Field(default=None, max_length=200)
    bug_severity: Severity = "medium"


class BugOut(BaseModel):
    id: str
    number: int = 0
    project_id: str
    project_name: str
    change_id: str
    change_commit: str
    title: str
    severity: Severity
    status: BugStatus
    created_at: datetime
    fixed_at: datetime | None
    fixed_by_commit: str | None


class BugFixIn(BaseModel):
    # The passing change that fixed it, if known.
    change_id: str | None = None


class TrendDay(BaseModel):
    day: date
    logged: int
    passed: int
    failed: int
    needs_review: int


class Kpi(BaseModel):
    value: int
    # The same measure for the period before, for the delta.
    previous: int
    # One point per day of the period, for the sparkline.
    series: list[int]


class Kpis(BaseModel):
    # Changes logged in the period.
    changes: Kpi
    # Verdicts recorded in the period.
    verified: Kpi
    # Bugs found in the period.
    bugs: Kpi
    # Every bug Riven remembers (open or fixed), at the end of each day.
    memories: Kpi


class Totals(BaseModel):
    projects: int
    changes: int
    pending: int
    passed: int
    failed: int
    needs_review: int
    open_bugs: int
    fixed_bugs: int


class DashboardOut(BaseModel):
    days: int
    project_id: str | None
    totals: Totals
    kpis: Kpis
    # Share of judged changes (passed + failed) that passed; None before any verdict.
    pass_rate: float | None
    by_producer: dict[ProducerKind, int]
    trend: list[TrendDay]
    recent: list[ChangeOut]
    # Changes still waiting for a final verdict (pending or needs review), newest first.
    active: list[ChangeOut]
    # The latest judged changes.
    runs: list[ChangeOut]
    open_bugs: list[BugOut]
    # Latest bugs with the change that introduced them and the change that fixed them.
    chains: list[BugOut]


ActivityKind = Literal["change_logged", "verdict", "bug_found", "bug_fixed"]


class ActivityItem(BaseModel):
    kind: ActivityKind
    at: datetime
    number: int
    title: str
    detail: str
    project_name: str
    status: ChangeStatus | BugStatus | None = None
