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


class RunState(StrEnum):
    """Lifecycle of one verification run (orchestrator)."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class LockStatus(StrEnum):
    ACTIVE = "active"
    RETIRED = "retired"


class NodeKind(StrEnum):
    """Causal graph node kinds (ticket S09.1)."""

    REQUIREMENT = "requirement"
    CHANGE = "change"
    MODULE = "module"
    SYMBOL = "symbol"
    BUG = "bug"
    FIX = "fix"
    TEST = "test"
    DECISION = "decision"


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
