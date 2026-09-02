from datetime import datetime
from typing import Any, Literal, cast

from pydantic import BaseModel, Field

from .config import settings


Provider = Literal["ollama", "openai", "anthropic"]
DEFAULT_PROVIDER = cast(Provider, settings.default_provider)


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    provider: Provider = DEFAULT_PROVIDER
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


class MemoryKnowledgeHit(BaseModel):
    id: str
    kind: str
    scope: str
    scope_id: str | None = None
    title: str
    content: str
    confidence: float
    source_ids: list[str] = Field(default_factory=list)
    score: float | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MemoryConsolidateRequest(BaseModel):
    conversation_id: str = Field(default="default", min_length=1, max_length=200)
    max_records: int = Field(default=100, ge=2, le=500)


class MemoryConsolidateResponse(BaseModel):
    conversation_id: str
    records_read: int
    knowledge_written: int
    knowledge: list[MemoryKnowledgeHit] = Field(default_factory=list)


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
    provider: Provider = DEFAULT_PROVIDER
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
    provider: Provider = DEFAULT_PROVIDER
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
    provider: Provider = DEFAULT_PROVIDER
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


class VoiceTranscription(BaseModel):
    text: str
    engine: str
    model: str
    language: str


class ToolProposalRequest(BaseModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolProposalResponse(BaseModel):
    approval_id: str
    tool: str
    arguments: dict[str, Any]
    expires_in_seconds: int


class ToolReadRequest(BaseModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolReadResponse(BaseModel):
    tool: str
    result: Any


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
    provider: Provider = DEFAULT_PROVIDER
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


class TaskArtifactView(BaseModel):
    id: str
    kind: str
    payload: Any
    created_at: datetime | None = None


class RunEventView(BaseModel):
    id: str
    sequence: int
    event_type: str
    payload: Any
    created_at: datetime | None = None


class TaskDetail(BaseModel):
    task: TaskSummary
    artifacts: list[TaskArtifactView] = Field(default_factory=list)
    events: list[RunEventView] = Field(default_factory=list)


class WorkerInfo(BaseModel):
    name: str
    type: Literal["builtin", "command", "http"]
    configured: bool = True
    detail: str = ""


class WorkerRunRequest(BaseModel):
    worker: str
    prompt: str = Field(min_length=1, max_length=50_000)
    provider: Provider = DEFAULT_PROVIDER
    model: str | None = None
    use_research: bool = False
    context: dict[str, Any] = Field(default_factory=dict)


class WorkerRunResponse(BaseModel):
    worker: str
    output: str
    task_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScheduleCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    request: TeamRunRequest
    interval_seconds: int = Field(ge=60, le=2_592_000)
    run_immediately: bool = False


class ScheduleInfo(BaseModel):
    id: str
    name: str
    enabled: bool
    request: TeamRunRequest
    interval_seconds: int
    next_run_at: datetime
    last_run_at: datetime | None = None
    last_task_id: str | None = None
    last_error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ScheduleToggleRequest(BaseModel):
    enabled: bool


class PromptEvalCase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    input: str = Field(min_length=1, max_length=10_000)
    expected_contains: list[str] = Field(default_factory=list, max_length=20)
    forbidden_contains: list[str] = Field(default_factory=list, max_length=20)


class EvolutionRunRequest(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    base_prompt: str = Field(min_length=1, max_length=30_000)
    cases: list[PromptEvalCase] = Field(min_length=1, max_length=10)
    provider: Provider = DEFAULT_PROVIDER
    model: str | None = None
    variants: int = Field(default=2, ge=1, le=3)


class EvolutionCaseResult(BaseModel):
    name: str
    passed: bool
    score: float
    missing: list[str] = Field(default_factory=list)
    forbidden_found: list[str] = Field(default_factory=list)


class EvolutionCandidateInfo(BaseModel):
    id: str
    name: str
    kind: str
    content: str
    status: str
    score: float | None = None
    baseline_score: float | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class EvolutionRunResponse(BaseModel):
    baseline_score: float
    candidates: list[EvolutionCandidateInfo]
    best_candidate_id: str | None = None
    notes: list[str] = Field(default_factory=list)


class EvolutionPromotionRequest(BaseModel):
    approved: bool = False
