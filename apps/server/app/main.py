from contextlib import asynccontextmanager
import json

from fastapi import FastAPI, HTTPException, Query
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
    MemoryClearResponse,
    MemoryDeleteResponse,
    MemoryHit,
    MemorySearchRequest,
    ToolExecuteRequest,
    ToolExecuteResponse,
    ToolProposalRequest,
    ToolProposalResponse,
    WorkspaceInfo,
    WorkspaceListResponse,
    WorkspaceSelectRequest,
)
from .services.agent import make_plan
from .services.approvals import approvals
from .services.builder import make_changes
from .services.llm_router import LLMError, router
from .services.memory import clear_memory, delete_memory, recent_memory, remember, search_memory
from .services.workspace_manager import workspace_manager
from .tools.registry import TOOLS, validate_tool


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    yield


app = FastAPI(title=settings.app_name, version="0.2.0", lifespan=lifespan)
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
        hits = await search_memory(last_user.content, request.conversation_id, limit=4)
        memory_context = [f"{hit.role}: {hit.content}" for hit in hits]
        if memory_context:
            messages.insert(
                0,
                ChatMessage(
                    role="system",
                    content="Relevant prior memory (may be imperfect; use only when helpful):\n" + "\n".join(memory_context),
                ),
            )
    return messages, last_user, memory_context


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "app": settings.app_name, "workspace": str(workspace_manager.path)}


@app.get("/v1/models")
async def models() -> dict:
    return {
        "providers": {
            "ollama": {"default_model": settings.ollama_chat_model, "configured": True},
            "openai": {"default_model": settings.openai_model, "configured": bool(settings.openai_api_key)},
            "anthropic": {"default_model": settings.anthropic_model, "configured": bool(settings.anthropic_api_key)},
        }
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


@app.get("/v1/memory", response_model=list[MemoryHit])
async def memory_recent(
    conversation_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[MemoryHit]:
    return await recent_memory(conversation_id, limit)


@app.post("/v1/memory/search", response_model=list[MemoryHit])
async def memory_search(request: MemorySearchRequest) -> list[MemoryHit]:
    return await search_memory(request.query, request.conversation_id, request.limit)


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
        return ToolExecuteResponse(tool=approval.tool, result=result)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (TypeError, ValueError, FileNotFoundError, FileExistsError, NotADirectoryError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
