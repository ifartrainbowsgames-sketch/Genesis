# Genesis architecture

## Design rules

Genesis is built around five rules:

1. **Local first.** Ollama is the default provider. Cloud models are optional adapters.
2. **User-owned memory.** Conversations and embeddings live in your PostgreSQL database.
3. **Visible plans.** The agent returns a plan before it touches files.
4. **Approval before mutation.** Tool calls that change state need explicit approval.
5. **Sandbox boundaries.** File tools are restricted to one workspace directory.

## Current request flow

### Chat

1. UI sends `/v1/chat`.
2. API stores the user message when the database is available.
3. Router calls the selected provider.
4. API stores the assistant response.
5. UI displays the response.

### Task planning

1. UI sends a natural-language goal to `/v1/agent/plan`.
2. The selected model converts the goal into structured JSON steps.
3. The plan is displayed but not executed automatically.
4. Future tool calls are proposed individually and must be approved.

### Tool approval

1. Client calls `/v1/tools/propose` with a tool name and arguments.
2. Server validates that the tool exists and returns a short-lived approval ID.
3. Client displays the exact action to the user.
4. User approves.
5. Client calls `/v1/tools/execute` with `approved: true` and the approval ID.
6. Server checks the approval and executes exactly that proposal once.

## Phase 2: coding workspace

Add tools for:

- `git.status`
- `git.diff`
- `git.apply_patch`
- `tests.run`
- `build.run`

Command execution should remain restricted to the selected repository and use a command policy rather than unrestricted shell access.

## Phase 3: desktop hub

Add a Tauri shell around the web UI and expose local-only capabilities through a permission broker. The desktop app should show:

- model selector
- active repository
- agent/task timeline
- pending approvals
- memory inspector
- terminal/test output
- Git changes

## Phase 4: multi-agent team

Use a shared task ledger instead of letting agents endlessly talk to each other. Suggested roles:

- Architect: converts goals into specifications and constraints.
- Builder: creates patches.
- Reviewer: checks diffs/tests and raises concrete issues.
- Researcher: gathers external information only when needed.

Every agent writes artifacts to the ledger. Agents do **not** recursively chat for its own sake.

## Phase 5: memory model

Split memory into:

- working memory: current task context
- episodic memory: prior sessions/events
- semantic memory: stable facts/preferences/projects
- artifact memory: files, diffs, decisions, test output

All memory should be inspectable and deletable by the user.
