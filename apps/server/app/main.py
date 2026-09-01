from contextlib import asynccontextmanager
import inspect
import json

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .config import settings
from .db import init_db
from .schemas import (
    AgentPlan,
    AgentPlanRequest,
    BuildRequest,
    ChangeSet,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    EvolutionCandidateInfo,
    EvolutionPromotionRequest,
    EvolutionRunRequest,
    EvolutionRunResponse,
    MemoryClearResponse,
    MemoryConsolidateRequest,
    MemoryConsolidateResponse,
    MemoryDeleteResponse,
    MemoryHit,
    MemoryKnowledgeHit,
    MemorySearchRequest,
    ResearchRequest,
    ResearchRunResponse,
    ScheduleCreateRequest,
    ScheduleInfo,
    ScheduleToggleRequest,
    TaskDetail,
    TaskSummary,
    TeamRunRequest,
    TeamRunResponse,
    ToolExecuteRequest,
    ToolExecuteResponse,
    ToolProposalRequest,
    ToolProposalResponse,
    ToolReadRequest,
    ToolReadResponse,
    VoiceTranscription,
    WorkerInfo,
    WorkerRunRequest,
    WorkerRunResponse,
    WorkspaceInfo,
    WorkspaceListResponse,
    WorkspaceSelectRequest,
)
from .services.agent import make_plan
from .services.approvals import approvals
from .services.builder import make_changes
from .services.evolution import list_candidates, promote_candidate, run_evolution
from .services.llm_router import LLMError, router
from .services.memory import clear_memory, delete_memory, recent_memory, remember, search_memory
from .services.memory_consolidator import consolidate_memory, recent_knowledge, search_knowledge
from .services.researcher import research
from .services.runtime import replay_request, task_detail
from .services.scheduler import (
    create_schedule,
    delete_schedule,
    list_schedules,
    run_due_schedules,
    set_schedule_enabled,
    start_scheduler,
    stop_scheduler,
)
from .services.system_health import system_health
from .services.task_ledger import add_artifact, create_task, finish_task, list_tasks
from .services.team import run_team
from .services.voice import transcribe_wav
from .services.workers import list_workers, run_worker
from .services.workspace_manager import workspace_manager
from .tools.registry import TOOLS, validate_tool


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    start_scheduler()
    try:
        yield
    finally:
        await stop_scheduler()


app = FastAPI(title=settings.app_name, version="0.9.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin, "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _workspace_info(candidate) -> WorkspaceInfo:
    return WorkspaceInfo(
        name=candidate.name,
        path=candidate.path,
        is_git=candidate.is_git,
        selected=candidate.selected,
    )


async def _chat_context(request: ChatRequest) -> tuple[list[ChatMessage], ChatMessage | None, list[str]]:
    messages = list(request.messages)
    memory_context: list[str] = []
    last_user = next((m for m in reversed(messages) if m.role == "user"), None)
    if request.use_memory and last_user:
        episodic = await search_memory(last_user.content, request.conversation_id, limit=3)
        knowledge = await search_knowledge(last_user.content, request.conversation_id, limit=3)
        memory_context.extend(f"{hit.role}: {hit.content}" for hit in episodic)
        memory_context.extend(f"{hit.kind}: {hit.content}" for hit in knowledge)
        if memory_context:
            messages.insert(
                0,
                ChatMessage(
                    role="system",
                    content=(
                        "Relevant prior memory and consolidated knowledge (may be imperfect; use only when helpful):\n"
                        + "\n".join(memory_context)
                    ),
                ),
            )
    return messages, last_user, memory_context


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "app": settings.app_name, "workspace": str(workspace_manager.path)}


@app.get("/v1/system/health")
async def system_health_endpoint() -> dict:
    return await system_health()


@app.get("/v1/models")
async def models() -> dict:
    return {
        "providers": {
            "ollama": {"default_model": settings.ollama_chat_model, "configured": True},
            "openai": {"default_model": settings.openai_model, "configured": bool(settings.openai_api_key)},
            "anthropic": {"default_model": settings.anthropic_model, "configured": bool(settings.anthropic_api_key)},
        },
        "voice": {
            "configured": bool(settings.whisper_cpp_binary and settings.whisper_cpp_model),
            "engine": "whisper.cpp",
        },
        "research": {
            "configured": bool(settings.searxng_url),
            "engine": "searxng",
        },
        "runtime": {
            "schedules": settings.scheduler_enabled,
            "external_workers": True,
            "cognitive_memory": True,
            "shadow_evolution": True,
        },
    }


@app.get("/v1/workspaces", response_model=WorkspaceListResponse)
async def workspaces() -> WorkspaceListResponse:
    return WorkspaceListResponse(
        current=_workspace_info(workspace_manager.describe()),
        candidates=[_workspace_info(item) for item in workspace_manager.discover()],
    )


@app.post("/v1/workspaces/select", response_model=WorkspaceInfo)
async def select_workspace(request: WorkspaceSelectRequest) -> WorkspaceInfo:
    try:
        return _workspace_info(workspace_manager.select(request.path))
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    messages, last_user, memory_context = await _chat_context(request)
    try:
        model, content = await router.chat(request.provider, messages, request.model)
    except (LLMError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if last_user:
        await remember(request.conversation_id, "user", last_user.content)
    await remember(request.conversation_id, "assistant", content)
    return ChatResponse(provider=request.provider, model=model, content=content, memory_context=memory_context)


@app.post("/v1/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    messages, last_user, memory_context = await _chat_context(request)
    model = request.model or router.default_model(request.provider)

    async def events():
        parts: list[str] = []
        try:
            resolved_model, stream = await router.stream(request.provider, messages, request.model)
            yield f"event: meta\ndata: {json.dumps({'provider': request.provider, 'model': resolved_model, 'memory_context': memory_context})}\n\n"
            async for text in stream:
                parts.append(text)
                yield f"event: delta\ndata: {json.dumps({'text': text})}\n\n"
            content = "".join(parts)
            if last_user:
                await remember(request.conversation_id, "user", last_user.content)
            if content:
                await remember(request.conversation_id, "assistant", content)
            yield f"event: done\ndata: {json.dumps({'model': resolved_model})}\n\n"
        except Exception as exc:
            yield f"event: error\ndata: {json.dumps({'message': str(exc)})}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "X-Genesis-Model": model},
    )


@app.post("/v1/voice/transcribe", response_model=VoiceTranscription)
async def voice_transcribe(request: Request, language: str = Query(default="auto", max_length=16)) -> VoiceTranscription:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type not in {"audio/wav", "audio/wave", "audio/x-wav", "application/octet-stream"}:
        raise HTTPException(status_code=415, detail="Voice endpoint accepts PCM WAV audio")
    audio = await request.body()
    try:
        return await transcribe_wav(audio, language)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/memory", response_model=list[MemoryHit])
async def memory_recent(
    conversation_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[MemoryHit]:
    return await recent_memory(conversation_id, limit)


@app.post("/v1/memory/search", response_model=list[MemoryHit])
async def memory_search(request: MemorySearchRequest) -> list[MemoryHit]:
    return await search_memory(request.query, request.conversation_id, request.limit)


@app.get("/v1/memory/knowledge", response_model=list[MemoryKnowledgeHit])
async def memory_knowledge(
    scope_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[MemoryKnowledgeHit]:
    return await recent_knowledge(scope_id, limit)


@app.post("/v1/memory/knowledge/search", response_model=list[MemoryKnowledgeHit])
async def memory_knowledge_search(request: MemorySearchRequest) -> list[MemoryKnowledgeHit]:
    return await search_knowledge(request.query, request.conversation_id, request.limit)


@app.post("/v1/memory/consolidate", response_model=MemoryConsolidateResponse)
async def memory_consolidate(request: MemoryConsolidateRequest) -> MemoryConsolidateResponse:
    return await consolidate_memory(request.conversation_id, request.max_records)


@app.delete("/v1/memory/{memory_id}", response_model=MemoryDeleteResponse)
async def memory_delete(memory_id: str) -> MemoryDeleteResponse:
    try:
        deleted = await delete_memory(memory_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MemoryDeleteResponse(deleted=deleted, id=memory_id)


@app.delete("/v1/memory", response_model=MemoryClearResponse)
async def memory_clear(conversation_id: str | None = Query(default=None)) -> MemoryClearResponse:
    deleted = await clear_memory(conversation_id)
    return MemoryClearResponse(deleted=deleted, conversation_id=conversation_id)


@app.post("/v1/research", response_model=ResearchRunResponse)
async def research_run(request: ResearchRequest) -> ResearchRunResponse:
    task_id = await create_task(f"Research: {request.query}", request.provider, request.model)
    try:
        report = await research(request)
        await add_artifact(task_id, "researcher_report", report.model_dump())
        await finish_task(task_id, "researched", f"Source-tracked research completed with {len(report.sources)} source(s)")
        return ResearchRunResponse(task_id=task_id, report=report)
    except Exception as exc:
        await finish_task(task_id, "failed", f"Research failed: {exc}")
        raise HTTPException(status_code=502, detail=f"Research failed: {exc}") from exc


@app.get("/v1/tasks", response_model=list[TaskSummary])
async def tasks(limit: int = Query(default=30, ge=1, le=100)) -> list[TaskSummary]:
    return await list_tasks(limit)


@app.get("/v1/tasks/{task_id}", response_model=TaskDetail)
async def task_detail_endpoint(task_id: str) -> TaskDetail:
    detail = await task_detail(task_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Task not found")
    return detail


@app.post("/v1/tasks/{task_id}/retry", response_model=TeamRunResponse)
async def task_retry(task_id: str) -> TeamRunResponse:
    payload = await replay_request(task_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Task has no replayable team request artifact")
    try:
        request = TeamRunRequest.model_validate(payload)
        return await run_team(request, retry_of=task_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Task retry failed: {exc}") from exc


@app.post("/v1/team/run", response_model=TeamRunResponse)
async def team_run(request: TeamRunRequest) -> TeamRunResponse:
    try:
        return await run_team(request)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Team run failed: {exc}") from exc


@app.get("/v1/workers", response_model=list[WorkerInfo])
async def workers() -> list[WorkerInfo]:
    try:
        return list_workers()
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/v1/workers/run", response_model=WorkerRunResponse)
async def workers_run(request: WorkerRunRequest) -> WorkerRunResponse:
    try:
        return await run_worker(request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (RuntimeError, ValueError, FileNotFoundError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/v1/schedules", response_model=list[ScheduleInfo])
async def schedules() -> list[ScheduleInfo]:
    return await list_schedules()


@app.post("/v1/schedules", response_model=ScheduleInfo)
async def schedules_create(request: ScheduleCreateRequest) -> ScheduleInfo:
    try:
        return await create_schedule(request)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Schedule creation failed: {exc}") from exc


@app.post("/v1/schedules/{schedule_id}/toggle", response_model=ScheduleInfo)
async def schedules_toggle(schedule_id: str, request: ScheduleToggleRequest) -> ScheduleInfo:
    result = await set_schedule_enabled(schedule_id, request.enabled)
    if not result:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return result


@app.delete("/v1/schedules/{schedule_id}")
async def schedules_delete(schedule_id: str) -> dict:
    deleted = await delete_schedule(schedule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"deleted": True, "id": schedule_id}


@app.post("/v1/schedules/run-due")
async def schedules_run_due() -> dict:
    return {"task_ids": await run_due_schedules()}


@app.post("/v1/agent/plan", response_model=AgentPlan)
async def agent_plan(request: AgentPlanRequest) -> AgentPlan:
    try:
        return await make_plan(request)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Planner failed: {exc}") from exc


@app.post("/v1/agent/build", response_model=ChangeSet)
async def agent_build(request: BuildRequest) -> ChangeSet:
    try:
        return await make_changes(request)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Builder failed: {exc}") from exc


@app.get("/v1/tools")
async def tools() -> dict:
    return {
        "tools": [
            {"name": name, "description": spec.description, "mutates": spec.mutates}
            for name, spec in sorted(TOOLS.items())
        ]
    }


@app.post("/v1/tools/read", response_model=ToolReadResponse)
async def read_tool(request: ToolReadRequest) -> ToolReadResponse:
    try:
        spec = validate_tool(request.tool)
        if spec.mutates:
            raise HTTPException(status_code=403, detail="Mutating tools require proposal and explicit approval")
        result = spec.fn(**request.arguments)
        if inspect.isawaitable(result):
            result = await result
        return ToolReadResponse(tool=request.tool, result=result)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (TypeError, ValueError, FileNotFoundError, FileExistsError, NotADirectoryError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/tools/propose", response_model=ToolProposalResponse)
async def propose_tool(request: ToolProposalRequest) -> ToolProposalResponse:
    try:
        validate_tool(request.tool)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    approval_id = approvals.create(request.tool, request.arguments)
    return ToolProposalResponse(
        approval_id=approval_id,
        tool=request.tool,
        arguments=request.arguments,
        expires_in_seconds=settings.approval_ttl_seconds,
    )


@app.post("/v1/tools/execute", response_model=ToolExecuteResponse)
async def execute_tool(request: ToolExecuteRequest) -> ToolExecuteResponse:
    if not request.approved:
        raise HTTPException(status_code=403, detail="Explicit approval is required")
    try:
        approval = approvals.consume(request.approval_id)
        spec = validate_tool(approval.tool)
        result = spec.fn(**approval.arguments)
        if inspect.isawaitable(result):
            result = await result
        return ToolExecuteResponse(tool=approval.tool, result=result)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (TypeError, ValueError, FileNotFoundError, FileExistsError, NotADirectoryError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/evolution/candidates", response_model=list[EvolutionCandidateInfo])
async def evolution_candidates(limit: int = Query(default=50, ge=1, le=100)) -> list[EvolutionCandidateInfo]:
    return await list_candidates(limit)


@app.post("/v1/evolution/run", response_model=EvolutionRunResponse)
async def evolution_run(request: EvolutionRunRequest) -> EvolutionRunResponse:
    try:
        return await run_evolution(request)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Evolution run failed: {exc}") from exc


@app.post("/v1/evolution/candidates/{candidate_id}/promote", response_model=EvolutionCandidateInfo)
async def evolution_promote(candidate_id: str, request: EvolutionPromotionRequest) -> EvolutionCandidateInfo:
    try:
        return await promote_candidate(candidate_id, request.approved)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
