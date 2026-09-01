from datetime import datetime
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
    limit: int = Field(default=5, ge=1, le=100)


class MemoryHit(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    score: float | None = None
    created_at: datetime | None = None


class MemoryDeleteResponse(BaseModel):
    deleted: bool
    id: str


class MemoryClearResponse(BaseModel):
    deleted: int
    conversation_id: str | None = None


class WorkspaceInfo(BaseModel):
    name: str
    path: str
    is_git: bool
    selected: bool = False


class WorkspaceListResponse(BaseModel):
    current: WorkspaceInfo
    candidates: list[WorkspaceInfo]


class WorkspaceSelectRequest(BaseModel):
    path: str


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


class ResearchSource(BaseModel):
    id: str
    title: str
    url: str
    snippet: str = ""
    engine: str | None = None
    score: float | None = None


class ResearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=4000)
    provider: Provider = "ollama"
    model: str | None = None
    max_results: int = Field(default=8, ge=1, le=12)
    language: str = Field(default="all", max_length=32)
    time_range: Literal["day", "month", "year"] | None = None
    safesearch: int = Field(default=1, ge=0, le=2)


class ResearchReport(BaseModel):
    query: str
    answer: str
    sources: list[ResearchSource] = Field(default_factory=list)
    provider: Provider
    model: str
    notes: list[str] = Field(default_factory=list)


class ResearchRunResponse(BaseModel):
    task_id: str
    report: ResearchReport


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


class ReviewIssue(BaseModel):
    severity: Literal["info", "warning", "blocking"] = "warning"
    file: str | None = None
    message: str


class ReviewReport(BaseModel):
    verdict: Literal["approve", "changes_requested"]
    summary: str
    issues: list[ReviewIssue] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class TeamRunRequest(BaseModel):
    task: str
    provider: Provider = "ollama"
    model: str | None = None
    max_agent_calls: int = Field(default=4, ge=1, le=4)
    use_research: bool = False
    research_query: str | None = Field(default=None, max_length=4000)
    research_max_results: int = Field(default=8, ge=1, le=12)


class TeamRunResponse(BaseModel):
    task_id: str
    plan: AgentPlan
    research: ResearchReport | None = None
    changes: ChangeSet | None = None
    review: ReviewReport | None = None
    stop_reason: str
    status: str


class TaskSummary(BaseModel):
    id: str
    title: str
    status: str
    provider: str
    model: str | None = None
    workspace: str
    stop_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
