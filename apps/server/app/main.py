from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import init_db
from .schemas import (
    AgentPlan,
    AgentPlanRequest,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    BuildRequest,
    ChangeSet,
    MemoryHit,
    MemorySearchRequest,
    ToolExecuteRequest,
    ToolExecuteResponse,
    ToolProposalRequest,
    ToolProposalResponse,
)
from .services.agent import make_plan
from .services.builder import make_changes
from .services.approvals import approvals
from .services.llm_router import LLMError, router
from .services.memory import remember, search_memory
from .tools.registry import TOOLS, validate_tool


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin, "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "app": settings.app_name}


@app.get("/v1/models")
async def models() -> dict:
    return {
        "providers": {
            "ollama": {"default_model": settings.ollama_chat_model, "configured": True},
            "openai": {"default_model": settings.openai_model, "configured": bool(settings.openai_api_key)},
            "anthropic": {"default_model": settings.anthropic_model, "configured": bool(settings.anthropic_api_key)},
        }
    }


@app.post("/v1/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
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

    try:
        model, content = await router.chat(request.provider, messages, request.model)
    except (LLMError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if last_user:
        await remember(request.conversation_id, "user", last_user.content)
    await remember(request.conversation_id, "assistant", content)

    return ChatResponse(
        provider=request.provider,
        model=model,
        content=content,
        memory_context=memory_context,
    )


@app.post("/v1/memory/search", response_model=list[MemoryHit])
async def memory_search(request: MemorySearchRequest) -> list[MemoryHit]:
    return await search_memory(request.query, request.conversation_id, request.limit)


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
