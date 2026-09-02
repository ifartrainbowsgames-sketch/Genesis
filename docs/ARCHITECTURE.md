# Genesis architecture

## Design rules

Genesis 0.9 is built around these rules:

1. **Local first.** Ollama is the default provider; cloud models are optional adapters.
2. **User-owned persistence.** Conversation memory, cognitive memory, tasks, events, schedules, and evolution history live in PostgreSQL/pgvector.
3. **Visible artifacts.** Plans, research, code proposals, reviews, tool results, and retry lineage are inspectable.
4. **Approval before mutation.** Local writes and side-effect-capable integrations require explicit approval.
5. **Workspace boundaries.** File access, project checks, and command-worker cwd stay inside the selected workspace.
6. **Bounded agents.** Team runs have a hard call budget and do not recursively converse.
7. **Explicit network/worker integrations.** GitHub, MCP, research, and external workers use configured adapters rather than unrestricted shell/network authority.
8. **Shadow-first evolution.** Candidate prompts are evaluated and stored before any manual promotion.

## Process layout

```text
Next.js UI / Tauri WebView
  |-- Workstation
  |-- Workbench (Explorer / Monaco / Git / output-only xterm)
  |-- Runtime (tasks / events / retries / schedules / workers)
  |-- Memory (episodic + cognitive)
  |-- Evolution (shadow candidates / deterministic eval / promotion)
  |-- Research / Voice / Connections / Diagnostics
  v
FastAPI :8000  <---- packaged as genesis-server sidecar for desktop
  |
  +--> model router ----------> Ollama / optional OpenAI / Anthropic
  +--> episodic memory -------> PostgreSQL + pgvector
  +--> cognitive memory ------> PostgreSQL + pgvector
  +--> durable runtime -------> tasks / artifacts / events / schedules
  +--> safe workspace --------> selected local root
  +--> approval broker -------> short-lived single-use approvals
  +--> worker registry -------> builtin team / fixed argv / allowlisted HTTP
  +--> GitHub adapter --------> configured GitHub token
  +--> MCP registry ----------> allowlisted Streamable HTTP servers
  +--> Researcher ------------> configured SearXNG broker
  +--> voice STT -------------> configured whisper.cpp CLI + model
  `--> evolution -------------> bounded candidates + deterministic eval history
```

## Chat and memory

1. UI sends a normal or streaming chat request.
2. Genesis retrieves bounded episodic matches from `memory_records`.
3. Genesis also retrieves bounded semantic/procedural matches from `memory_knowledge`.
4. Retrieved context is inserted as imperfect supporting memory, not as trusted instructions.
5. The model request is routed to Ollama/OpenAI/Anthropic.
6. Completed user/assistant turns are appended to episodic memory when PostgreSQL is available.

Cognitive consolidation is separate from raw chat storage. V1 consolidation creates an inspectable semantic summary and user-stated procedural constraints/preferences while retaining source record IDs. Original episodes are not deleted or rewritten.

## Workbench and tool authority

`/workbench` uses the registered tool layer rather than bypassing it.

Read-only operations such as workspace listing/reading and Git diff/status use `/v1/tools/read`. That endpoint refuses any registered tool marked `mutates=True`.

Writes/checks follow:

```text
UI action
  -> /v1/tools/propose (tool + exact args)
  -> short-lived approval id
  -> explicit user confirmation
  -> /v1/tools/execute
  -> server consumes approval once
  -> stored tool + stored args execute
```

The client cannot replace arguments after approval.

The Workbench xterm surface displays output from the fixed project-check runner only. `disableStdin` is enabled and there is no registered general shell tool.

Recursive Explorer scans skip `.git`, dependency trees, virtual environments, build output, Rust `target`, and cache directories.

## Bounded team

`POST /v1/team/run` performs one bounded pass with a maximum four model calls:

```text
Architect -> [Researcher] -> Builder -> Reviewer -> STOP
```

Each completed role writes an artifact. A `team_request` artifact records the immutable request needed for replay. Ordered `RunEvent` rows record role/task transitions. Reviewer approval means `awaiting_approval`, not automatic workspace mutation.

## Durable runtime and replay

A task consists of:

- `TaskRecord`: identity, provider/model, workspace, status, stop reason
- `TaskArtifact`: immutable structured handoffs/results
- `RunEvent`: ordered execution history

`GET /v1/tasks/{id}` returns the task, artifacts, and events. Retry loads the original `team_request`, creates a new task, and records a `retry_of` artifact; the prior run remains unchanged.

## Schedules

Schedules are PostgreSQL records containing a bounded `TeamRunRequest`, interval, next/last run timestamps, and last result/error references.

The scheduler:

1. selects due enabled records;
2. claims them with `FOR UPDATE SKIP LOCKED`;
3. advances `next_run_at` before launching work;
4. commits the claim;
5. executes the bounded team;
6. stores last task/error metadata.

This prevents a slow run from being repeatedly picked up by concurrent scheduler iterations. Scheduled team runs still stop before workspace mutation.

## External worker boundary

`EXTERNAL_WORKERS_JSON` is parsed server-side. Workers are not discovered from the machine automatically.

### Command workers

A command worker defines a fixed argv array and optional workspace-relative cwd. Genesis launches it using `asyncio.create_subprocess_exec`; there is no shell. The prompt/context is sent on stdin rather than interpolated into a command string.

### HTTP workers

An HTTP worker defines an explicit HTTP(S) URL. Optional bearer-token material is read from a named environment variable and kept server-side.

### Execution rule

`/v1/workers/run` accepts only the built-in `genesis-team`. External command/HTTP workers execute through the registered mutating `worker.run` tool and therefore require the same approval broker as other side effects.

## Researcher

The Researcher has no general browser or shell. `research_broker.py` sends queries only to configured SearXNG and accepts bounded HTTP(S) result URLs. Results are deduplicated and assigned stable source IDs such as `S1`.

The selected model receives result titles/URLs/snippets and is instructed to preserve source IDs on source-dependent claims. Standalone reports and team research handoffs are stored as artifacts.

## Voice

The browser records audio and sends bounded PCM WAV. The backend resolves only configured `WHISPER_CPP_BINARY` and `WHISPER_CPP_MODEL` paths and launches whisper.cpp with a fixed transcription argument shape. The browser can inspect/edit the transcript before chat submission.

## GitHub adapter

GitHub credentials remain in FastAPI. Registered operations cover metadata, directory/file reads, SHA-safe create/replace, branch creation, and pull requests. Existing file replacement re-checks the observed SHA and refuses a stale update.

## MCP adapter

The registry supports explicitly configured Streamable HTTP MCP endpoints only. Callers select a configured server name rather than supplying arbitrary URLs. `mcp.call_tool` is side-effect-capable and approval-gated.

## Evolution V1

Evolution is an evaluation subsystem, not an autonomous self-modification loop.

1. User supplies a baseline system prompt and deterministic eval cases.
2. Baseline runs against the selected provider/model.
3. The model may generate at most `EVOLUTION_MAX_VARIANTS` bounded prompt variants.
4. Each variant runs on the same cases.
5. Scoring checks expected substrings and forbidden substrings deterministically.
6. Candidate score, baseline score, case results, latency, provider/model, and status are persisted.
7. Candidates remain `shadow` by default.
8. Manual promotion succeeds only when all deterministic cases passed and score meets/beats baseline.

Promotion records a selected candidate; it does not automatically rewrite project files or runtime configuration.

## Desktop sidecar and release

`scripts/build-sidecar.ps1` packages FastAPI with PyInstaller, names the sidecar for the Rust target triple, and places it in Tauri's external-binary directory. Tauri launches the sidecar at desktop startup.

PR CI now verifies four layers:

- Python compile/pytest against real PostgreSQL + pgvector
- Next.js production/static-export build
- Windows PyInstaller sidecar packaging **and actual packaged `/health` runtime smoke**
- Tauri/Rust compile check

Tagged `v*` pushes build the Windows bundles, upload the workflow artifact, create a GitHub Release, and attach generated bundle files.

A produced installer is not represented as Authenticode-signed unless a real signing identity/certificate is provided to the release environment.

## Startup and diagnostics

`scripts/doctor.ps1` checks local prerequisites and, when the API is running, displays component health. `scripts/start.ps1` can bring up PostgreSQL/pgvector and SearXNG with Docker Compose, check Ollama availability, start API/web processes, and poll `/health` for readiness.

`/diagnostics` reports database, Ollama, research, voice, GitHub, MCP, worker registry, scheduler, cognitive memory, and evolution state without returning secret values.

## Database compatibility

Genesis 0.9 adds new tables (`memory_knowledge`, `run_events`, `schedule_records`, `evolution_candidates`, `evolution_eval_runs`) instead of modifying columns on existing Phase-5A tables. This keeps `Base.metadata.create_all()` safe for the 0.9 upgrade path. A formal migration framework should be introduced before future releases need destructive/column-changing schema migrations.
