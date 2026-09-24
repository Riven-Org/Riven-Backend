from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class ProducerKind(StrEnum):
    """Who produced a change. Needed to enforce 'Riven never approves its own work'."""

    HUMAN = "human"
    AI_AGENT = "ai_agent"
    BOT = "bot"
    UNKNOWN = "unknown"


class VerificationStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"


class VerificationStage(StrEnum):
    """Pipeline stages, in order (MVP flow)."""

    CAPTURE = "capture"
    ANALYZE = "analyze"
    SANDBOX = "sandbox"
    VERIFY = "verify"
    MEMORY = "memory"
    GRAPH = "graph"


class BugState(StrEnum):
    """Bug lifecycle (ticket S08.2)."""

    NEW = "new"
    CONFIRMED = "confirmed"
    FIXING = "fixing"
    FIX_VERIFIED = "fix_verified"
    LOCKED = "locked"
    REOPENED = "reopened"


class Producer(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: ProducerKind
    identity: str
    agent_model: str | None = None


class ChangeRef(BaseModel):
    """Identifies one change (commit or PR) in one repository."""

    model_config = ConfigDict(frozen=True)

    org_id: str
    repo: str
    commit_sha: str
    pr_number: int | None = None
