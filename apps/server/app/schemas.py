from typing import Any, Literal

from pydantic import BaseModel, Field


Provider = Literal["ollama", "openai", "anthropic"]


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    provider: Provider = "ollama"
    model: str | None = None
    conversation_id: str = "default"
    use_memory: bool = True


class ChatResponse(BaseModel):
    provider: Provider
    model: str
    content: str
    memory_context: list[str] = Field(default_factory=list)


class MemorySearchRequest(BaseModel):
    query: str
    conversation_id: str | None = None
    limit: int = Field(default=5, ge=1, le=20)


class MemoryHit(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    score: float | None = None


class AgentPlanRequest(BaseModel):
    task: str
    provider: Provider = "ollama"
    model: str | None = None


class AgentStep(BaseModel):
    id: int
    title: str
    description: str
    tool: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)


class AgentPlan(BaseModel):
    goal: str
    steps: list[AgentStep]
    notes: list[str] = Field(default_factory=list)


class BuildRequest(BaseModel):
    task: str
    provider: Provider = "ollama"
    model: str | None = None


class FileChange(BaseModel):
    path: str
    action: Literal["create", "replace"]
    content: str
    reason: str = ""


class RecommendedCheck(BaseModel):
    kind: Literal["python_compile", "python_test", "npm_build", "npm_test", "cargo_check", "cargo_test"]
    cwd: str = "."


class ChangeSet(BaseModel):
    summary: str
    files: list[FileChange]
    recommended_checks: list[RecommendedCheck] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ToolProposalRequest(BaseModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolProposalResponse(BaseModel):
    approval_id: str
    tool: str
    arguments: dict[str, Any]
    expires_in_seconds: int


class ToolExecuteRequest(BaseModel):
    approval_id: str
    approved: bool = False


class ToolExecuteResponse(BaseModel):
    tool: str
    result: Any
