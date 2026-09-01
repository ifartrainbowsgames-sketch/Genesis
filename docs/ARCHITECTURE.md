# Genesis architecture

## Design rules

Genesis is built around six rules:

1. **Local first.** Ollama is the default provider. Cloud models are optional adapters.
2. **User-owned memory.** Conversations and embeddings live in your PostgreSQL database and can be inspected or deleted.
3. **Visible plans.** The agent returns a plan before it touches files.
4. **Approval before mutation.** File-changing tools need explicit user approval.
5. **Sandbox boundaries.** File and build tools are restricted to the selected workspace.
6. **Bounded repository selection.** The UI can switch repositories only inside `WORKSPACE_ALLOWED_ROOTS`.

## Current request flow

### Streaming chat

1. UI sends `/v1/chat/stream`.
2. API retrieves relevant memory when enabled.
3. Router opens a provider-native streaming request.
4. API emits SSE `meta`, `delta`, and `done` events.
5. The completed user/assistant turn is stored in PostgreSQL when available.

### Repository selection

1. Genesis starts with `WORKSPACE_ROOT`.
2. `WORKSPACE_ALLOWED_ROOTS` defines folders the repository picker may browse.
3. `/v1/workspaces` discovers Git repositories under those roots with a depth/size cap.
4. `/v1/workspaces/select` changes the active workspace for the running process.
5. Every file, Git, and build tool resolves paths against that selected root.

### Task planning and building

1. UI sends a natural-language goal to `/v1/agent/plan`.
2. The selected model converts the goal into structured steps.
3. `/v1/agent/build` returns a concrete multi-file change set.
4. The UI previews exact file contents.
5. The user approves the change set.
6. Genesis applies the files atomically within the selected workspace.
7. Restricted checks and Git diff/status can be run from the activity panel.

### Tool approval

1. Client calls `/v1/tools/propose` with a tool name and arguments.
2. Server validates the tool and returns a short-lived approval ID.
3. The client displays or initiates the exact approved action.
4. Client calls `/v1/tools/execute` with `approved: true`.
5. Server consumes the approval exactly once.

## Phase 3: integrations

Add explicit adapters instead of unrestricted network or shell access:

- GitHub repository read/write and PR workflows
- MCP registry with per-server permissions
- optional web research broker with source tracking
- voice input/output

## Bounded multi-agent team

Genesis now has a bounded team workflow backed by a task ledger:

1. **Architect** converts the goal into a structured plan.
2. **Builder** produces an exact proposed multi-file change set.
3. **Reviewer** returns an approve/changes-requested verdict with concrete issues.
4. Every role writes an artifact to the task ledger.
5. The run stops after the configured 1–3 agent-call budget; there is no recursive agent conversation.
6. Even an approved Reviewer result still stops at `awaiting_approval`. A human must approve before files are applied.

`POST /v1/team/run` executes this single bounded pass. `GET /v1/tasks` exposes recent task-ledger entries. The Researcher role remains a later integration so outside information is fetched only through explicit, source-tracked adapters.

## Memory model target

Split memory into:

- working memory: current task context
- episodic memory: prior sessions/events
- semantic memory: stable facts/preferences/projects
- artifact memory: files, diffs, decisions, test output

All memory remains inspectable and deletable by the user.
