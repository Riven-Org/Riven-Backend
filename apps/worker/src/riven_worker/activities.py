"""Pipeline stage activities (ticket S01.2).

Each stage is a separate activity so Temporal can retry it on its own and resume
the run after a crash. Bodies are placeholders; each names the ticket that fills it in.
"""

from temporalio import activity

from riven_schemas import ChangeRef, StageResult, VerificationStage


@activity.defn
async def analyze_change(change: ChangeRef) -> StageResult:
    # S05.2: map the diff to changed functions/modules; load related bugs and locks.
    return StageResult(stage=VerificationStage.ANALYZE, ok=True, detail="not implemented")


@activity.defn
async def run_in_sandbox(change: ChangeRef) -> StageResult:
    # S06.1–S06.5: build the environment and run tests in an isolated sandbox.
    return StageResult(stage=VerificationStage.SANDBOX, ok=True, detail="not implemented")


@activity.defn
async def verify(change: ChangeRef) -> StageResult:
    # S07.1–S07.6: run verifier plugins and apply the verdict policy.
    return StageResult(stage=VerificationStage.VERIFY, ok=True, detail="not implemented")


@activity.defn
async def update_memory(change: ChangeRef) -> StageResult:
    # S08.1–S08.5: fingerprint failures, update bug memory, check regression locks.
    return StageResult(stage=VerificationStage.MEMORY, ok=True, detail="not implemented")


@activity.defn
async def update_graph(change: ChangeRef) -> StageResult:
    # S09.2: write causal-graph edges for this change.
    return StageResult(stage=VerificationStage.GRAPH, ok=True, detail="not implemented")


ALL_ACTIVITIES = [analyze_change, run_in_sandbox, verify, update_memory, update_graph]
