from __future__ import annotations

from ..schemas import AgentPlanRequest, BuildRequest, TeamRunRequest, TeamRunResponse
from .agent import make_plan
from .builder import make_changes
from .reviewer import review_changes
from .task_ledger import add_artifact, create_task, finish_task


async def run_team(request: TeamRunRequest) -> TeamRunResponse:
    task_id = await create_task(request.task, request.provider, request.model)
    calls = 0
    try:
        plan = await make_plan(AgentPlanRequest(task=request.task, provider=request.provider, model=request.model))
        calls += 1
        await add_artifact(task_id, "architect_plan", plan.model_dump())

        if calls >= request.max_agent_calls:
            stop_reason = f"Agent-call budget reached after Architect ({calls}/{request.max_agent_calls})"
            await finish_task(task_id, "planned", stop_reason)
            return TeamRunResponse(task_id=task_id, plan=plan, stop_reason=stop_reason, status="planned")

        changes = await make_changes(BuildRequest(task=request.task, provider=request.provider, model=request.model))
        calls += 1
        await add_artifact(task_id, "builder_changes", changes.model_dump())

        if calls >= request.max_agent_calls:
            stop_reason = f"Agent-call budget reached after Builder ({calls}/{request.max_agent_calls}); human review required"
            await finish_task(task_id, "awaiting_approval", stop_reason)
            return TeamRunResponse(task_id=task_id, plan=plan, changes=changes, stop_reason=stop_reason, status="awaiting_approval")

        review = await review_changes(request.task, changes, request.provider, request.model)
        calls += 1
        await add_artifact(task_id, "reviewer_report", review.model_dump())

        blocking = any(issue.severity == "blocking" for issue in review.issues)
        status = "needs_revision" if blocking or review.verdict == "changes_requested" else "awaiting_approval"
        stop_reason = (
            f"Reviewer requested changes; team stopped after one bounded pass ({calls}/{request.max_agent_calls})"
            if status == "needs_revision"
            else f"Reviewer approved proposal; waiting for human approval ({calls}/{request.max_agent_calls})"
        )
        await finish_task(task_id, status, stop_reason)
        return TeamRunResponse(
            task_id=task_id,
            plan=plan,
            changes=changes,
            review=review,
            stop_reason=stop_reason,
            status=status,
        )
    except Exception as exc:
        stop_reason = f"Team stopped on error after {calls} agent call(s): {exc}"
        await finish_task(task_id, "failed", stop_reason)
        raise
