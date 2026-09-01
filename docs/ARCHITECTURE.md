# Genesis architecture

## Design rules

Genesis is built around these rules:

1. **Local first.** Ollama is the default provider. Cloud models are optional adapters.
2. **User-owned memory.** Conversations and embeddings live in PostgreSQL/pgvector and can be inspected or deleted.
3. **Visible plans.** Coding agents return artifacts before anything is applied.
4. **Approval before mutation.** File-changing and external side-effect-capable tools require an approved tool execution.
5. **Sandbox boundaries.** Local file and build tools are restricted to the selected workspace.
6. **Bounded repository selection.** The UI can switch repositories only inside `WORKSPACE_ALLOWED_ROOTS`.
7. **Explicit network integrations.** GitHub and MCP are adapters with configured destinations, not general unrestricted network or shell access.

## Streaming chat

1. UI sends `/v1/chat/stream`.
2. API retrieves relevant memory when enabled.
3. Router opens a provider-native streaming request.
4. API emits SSE `meta`, `delta`, and `done` events.
5. The completed user/assistant turn is stored in PostgreSQL when available.

## Local repository selection

1. Genesis starts with `WORKSPACE_ROOT`.
2. `WORKSPACE_ALLOWED_ROOTS` defines folders the repository picker may browse.
3. `/v1/workspaces` discovers Git repositories under those roots with depth and result caps.
4. `/v1/workspaces/select` changes the active workspace for the running process.
5. File, Git, Builder context, and restricted build tools resolve against that selected root.

## Task planning and building

1. `/v1/agent/plan` asks the Architect for structured steps.
2. `/v1/agent/build` asks the Builder for an exact multi-file proposal.
3. The UI previews the full file contents.
4. The user approves the change set.
5. Genesis applies files atomically inside the selected workspace.
6. Restricted checks and Git diff/status can be run afterward.

## Tool approval broker

1. Client calls `/v1/tools/propose` with a registered tool and exact arguments.
2. Server validates the tool and returns a short-lived approval ID.
3. A user action approves the operation.
4. Client calls `/v1/tools/execute` with `approved: true`.
5. Server consumes the approval exactly once.
6. The broker supports both synchronous and asynchronous registered tools.

## GitHub adapter

The GitHub adapter is server-side and optional. `GITHUB_TOKEN` is never sent to the web UI.

Registered tools include:

- `github.repo_info`
- `github.list_dir`
- `github.read_file`
- `github.upsert_file`
- `github.create_branch`
- `github.create_pull_request`

Existing-file replacement requires `expected_sha`. Genesis reads the current remote SHA immediately before the update and rejects the write if it no longer matches. This prevents a stale preview from silently overwriting a newer remote change.

## MCP v2 adapter

Genesis uses the MCP Python SDK v2. The registry intentionally supports **Streamable HTTP only** for now; it does not launch arbitrary stdio commands.

`MCP_SERVERS_JSON` contains the explicit server allowlist. A tool request supplies a configured server **name**, not an arbitrary URL. The server name is resolved by `mcp_registry.py`, which validates the configured HTTP(S) URL and rejects unknown or disabled entries.

Registered MCP tools are:

- `mcp.servers` — show configured endpoints
- `mcp.list_tools` — negotiate with the selected MCP server and inspect advertised tool schemas
- `mcp.call_tool` — re-list tools, verify the requested tool is actually advertised, then call it

`mcp.call_tool` is classified as side-effect-capable and goes through the approval broker. Genesis uses the SDK's automatic protocol-version negotiation, allowing the SDK to handle modern MCP protocol details rather than hand-rolling wire messages.

The `/connections` UI provides the GitHub and MCP controls while keeping credentials in the FastAPI process.

## Bounded multi-agent team

Genesis uses a task ledger instead of unbounded agent-to-agent conversation:

1. **Architect** converts the goal into a structured plan.
2. **Builder** produces a proposed multi-file change set.
3. **Reviewer** returns an approve/changes-requested verdict with concrete findings.
4. Every role writes an artifact to the task ledger.
5. Runs stop after the configured 1–3 agent-call budget.
6. Reviewer approval still stops at `awaiting_approval`; a human approves before local files are changed.

`POST /v1/team/run` executes one bounded pass. `GET /v1/tasks` exposes recent ledger entries.

## Next integration: Researcher

The Researcher should not receive a general-purpose browser or shell. The planned broker will return source-tracked research artifacts from explicitly supported providers, then store the artifact in the task ledger for Architect/Builder consumption.

## Memory model target

The next memory split is:

- working memory: current task context
- episodic memory: prior sessions/events
- semantic memory: stable facts/preferences/projects
- artifact memory: files, diffs, decisions, test output, research artifacts

All persistent memory remains inspectable and deletable by the user.
