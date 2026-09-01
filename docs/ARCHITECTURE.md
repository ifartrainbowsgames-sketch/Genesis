# Genesis architecture

## Design rules

Genesis is built around these rules:

1. **Local first.** Ollama is the default provider; cloud models are optional adapters.
2. **User-owned memory.** Conversation and task data lives in the user's PostgreSQL/pgvector database.
3. **Visible artifacts.** Plans, research, code proposals, reviews, and tool results are inspectable.
4. **Approval before mutation.** Local code changes and external side-effect-capable tools require explicit user action.
5. **Sandbox boundaries.** Local file and project-check tools are restricted to the selected workspace.
6. **Bounded agents.** Team runs have a hard call budget and do not recursively converse.
7. **Explicit network integrations.** GitHub, MCP, and research use configured adapters rather than unrestricted network/shell access.
8. **Dedicated local executables.** Voice uses only a configured whisper.cpp binary/model, not a general command runner.

## Process layout

```text
Next.js UI / Tauri WebView
        |
        v
FastAPI :8000  <---- packaged as genesis-server sidecar for desktop
   |
   +--> model router -------> Ollama / optional OpenAI / Anthropic
   +--> memory -------------> PostgreSQL + pgvector
   +--> coding tools -------> selected local workspace
   +--> GitHub adapter -----> configured GitHub token
   +--> MCP registry -------> allowlisted Streamable HTTP servers
   +--> Researcher ---------> configured SearXNG broker
   +--> voice STT ----------> configured whisper.cpp CLI + model
```

## Streaming chat

1. UI sends `/v1/chat/stream`.
2. API retrieves relevant memory when enabled.
3. Router opens the selected provider's streaming request.
4. API emits SSE `meta`, `delta`, and `done` events.
5. Completed turns are stored when the database is available.

## Local repository selection

1. Genesis starts with `WORKSPACE_ROOT`.
2. `WORKSPACE_ALLOWED_ROOTS` defines folders the picker may browse.
3. `/v1/workspaces` discovers bounded candidate repositories.
4. `/v1/workspaces/select` changes the active workspace for the process.
5. File, Git, Builder-context, and restricted project-check paths resolve against that selected root.

## Coding and approval flow

1. Architect returns a structured plan.
2. Optional Researcher returns a source-tracked artifact.
3. Builder returns an exact multi-file change set.
4. Reviewer returns an approve/changes-requested report.
5. Genesis stops at review; nothing is automatically applied.
6. The UI displays proposed file contents.
7. User approval creates/consumes a short-lived single-use approval token.
8. Files are applied inside the selected workspace, after which restricted checks and Git diff/status can run.

## Bounded team

`POST /v1/team/run` performs one bounded pass. The maximum budget is four model calls:

```text
Architect -> [Researcher] -> Builder -> Reviewer -> STOP
```

Research is optional, so a normal coding pass still needs only Architect → Builder → Reviewer. Every completed role writes an artifact to the task ledger. Reviewer approval means `awaiting_approval`, not automatic execution.

## Researcher

The Researcher has no general browser or shell. `research_broker.py` sends a query only to `SEARXNG_URL` and requests SearXNG JSON results. It accepts only HTTP(S) result URLs, deduplicates them, and returns bounded source records with stable IDs such as `S1`.

`researcher.py` gives the selected model only those result titles, URLs, and snippets. The system prompt requires source IDs such as `[S1]` in source-dependent claims and records warnings if a synthesis omits citations or invents unknown IDs.

`POST /v1/research` stores the report as a `researcher_report` task artifact. A team run can pass the same research artifact to Builder as supporting context.

## Voice

The `/voice` page records microphone samples in the browser, down-samples them to 16 kHz mono PCM, and encodes a WAV payload. `POST /v1/voice/transcribe` accepts only WAV-like content types and enforces a maximum payload size.

`voice.py` resolves only `WHISPER_CPP_BINARY` and `WHISPER_CPP_MODEL`, validates both paths, writes the incoming WAV to a temporary directory, and launches whisper.cpp with a fixed transcription argument set. There is no arbitrary command parameter supplied by the browser.

The transcript is returned to the UI for inspection/editing before it is sent to chat. Optional spoken replies use the browser/operating-system `speechSynthesis` implementation.

## Tool approval broker

1. Client sends a registered tool name and exact arguments to `/v1/tools/propose`.
2. Server validates the tool and returns a short-lived approval ID.
3. A user action approves the exact operation.
4. Client sends the approval ID to `/v1/tools/execute` with `approved: true`.
5. Server consumes the token exactly once.
6. The broker supports both synchronous and asynchronous registered tools.

No general shell tool is registered.

## GitHub adapter

`GITHUB_TOKEN` stays in the FastAPI process. Registered operations cover repository metadata, directory/file reads, SHA-safe file create/replace, branch creation, and pull requests. Existing-file replacement requires `expected_sha`; Genesis re-reads the remote SHA immediately before update and rejects stale writes.

## MCP v2 adapter

The MCP registry supports explicitly configured **Streamable HTTP** servers only. `MCP_SERVERS_JSON` maps trusted names to URLs; callers choose a configured name rather than supplying an arbitrary URL.

Genesis can list configured servers, discover advertised tools, and call an advertised tool. `mcp.call_tool` is classified as side-effect-capable and goes through the approval broker.

## Desktop sidecar

The desktop build uses Tauri `bundle.externalBin` for `genesis-server`. `scripts/build-sidecar.ps1` packages `apps/server/sidecar_entry.py` with PyInstaller and names the output with the current Rust target triple, matching Tauri's sidecar convention.

The Rust desktop setup initializes `tauri-plugin-shell` and starts `genesis-server` when the desktop app launches. This bundles the FastAPI process with the app, but external local services remain explicit:

- PostgreSQL/pgvector for persistent memory/task data
- Ollama for local language models
- SearXNG for source-tracked web research
- whisper.cpp for local speech-to-text when configured

Windows CI packages the Python sidecar and runs `cargo check` so Rust-side sidecar wiring is compile-tested. Installer signing and first-run dependency setup remain release-hardening work.

## Memory evolution

Current persistent memory is conversation memory plus task-ledger artifacts. The next split is:

- working memory: current task context
- episodic memory: prior sessions/events
- semantic memory: stable facts/preferences/projects
- artifact memory: files, diffs, decisions, test output, research reports

Persistent memory should remain inspectable and deletable by the user.
