# Genesis architecture

## Design rules

Genesis 0.10 follows these rules:

1. **Local-first, not local-only.** Ollama is the default path; OpenAI and Anthropic are explicit alternatives.
2. **Desktop must be self-contained.** The installed Windows app owns its FastAPI sidecar and embedded durable database; Docker/PostgreSQL are not desktop prerequisites.
3. **Visible artifacts.** Plans, research, code proposals, reviews, tool results, and retry lineage are inspectable.
4. **Approval before mutation.** Model-generated work stops before side effects; registered mutating tools require explicit approval.
5. **Workspace boundaries.** File access, project checks, and command-worker cwd remain inside the selected workspace.
6. **Bounded agents.** Team runs have a hard call budget; Genesis does not create a conversational swarm.
7. **Explicit integrations.** GitHub, MCP, research, and external workers use configured adapters rather than general shell/network authority.
8. **Shadow-first evolution.** Candidates are evaluated and stored before manual promotion.
9. **Repairable startup.** Saved setup state is verified at launch instead of being trusted indefinitely.

## Installed Windows flow

```text
NSIS installer
  -> installs Genesis + packaged FastAPI sidecar
  -> launches Genesis.exe --installer-setup
  -> native setup bridge
       |-- hardware profile / model recommendation
       |-- Ollama detect/install/start/pull
       |-- OR exact cloud credential+model validation
       |-- project folder picker
       `-- native final verifier
  -> installer completes only after required checks pass
  -> normal Genesis launch
       |-- re-run native verifier
       |-- unhealthy -> /setup (repair)
       `-- healthy -> start sidecar -> wait /health -> /workbench
```

Silent NSIS installs do not open an interactive wizard. They defer setup until the first normal launch.

## Process layout

```text
Tauri WebView / Next.js static UI
  |-- Setup / Repair
  |-- Workbench (Explorer / Monaco / Git / output-only xterm)
  |-- Runtime (tasks / events / retries / schedules / workers)
  |-- Memory (episodic + cognitive)
  |-- Evolution (shadow candidates / deterministic eval / promotion)
  |-- Research / Voice / Connections / Diagnostics
  v
Packaged FastAPI sidecar :8000 (loopback)
  |
  +--> model router ----------> Ollama / OpenAI / Anthropic
  +--> durable storage -------> desktop SQLite OR PostgreSQL/pgvector
  +--> safe workspace --------> selected local root
  +--> approval broker -------> short-lived single-use approvals
  +--> worker registry -------> bounded team / fixed argv / allowlisted HTTP
  +--> GitHub adapter --------> configured server-side credential
  +--> MCP registry ----------> allowlisted Streamable HTTP servers
  +--> Researcher ------------> configured SearXNG
  +--> voice STT -------------> configured whisper.cpp
  `--> evolution -------------> bounded candidates + deterministic eval history
```

## Durable storage backends

Genesis uses one SQLAlchemy model set with backend-specific behavior.

### Installed desktop — SQLite

Tauri creates a private app-data path and starts the sidecar with:

```text
DATABASE_URL=sqlite+aiosqlite:///.../genesis.db
```

SQLite persists:

- `MemoryRecord`
- `MemoryKnowledge`
- `TaskRecord`
- `TaskArtifact`
- `RunEvent`
- `ScheduleRecord`
- `EvolutionCandidate`
- `EvolutionEvalRun`

Embedding columns use SQLAlchemy's pgvector type on PostgreSQL and JSON arrays on SQLite. When an embedding is available on SQLite, Genesis scans a bounded recent candidate set and ranks it in-process with cosine similarity. If embeddings are unavailable (for example, a cloud-only install without Ollama), text matching remains available.

The desktop scheduler has one sidecar process. An in-process claim lock prevents the background loop and manual run-due endpoint from claiming the same schedule simultaneously; `next_run_at` advances before the model run begins.

### Source/server — PostgreSQL + pgvector

Source/server mode keeps native PostgreSQL UUID/vector behavior. Vector search uses pgvector cosine-distance expressions. Schedules use `FOR UPDATE SKIP LOCKED` to support multiple scheduler processes safely.

`Base.metadata.create_all()` remains sufficient for the additive schemas used through 0.10. A formal migration framework is still required before a future release performs destructive or column-changing schema migrations.

## Chat and memory

1. UI sends chat or streaming chat.
2. Genesis retrieves bounded episodic matches.
3. Genesis retrieves bounded consolidated semantic/procedural matches.
4. Retrieved memory is labeled as imperfect supporting context, not trusted instruction.
5. Request routes to the installer/source-selected provider.
6. Completed turns append to durable episodic memory.

Cognitive consolidation preserves the original episodes, stores source-record IDs, and creates inspectable semantic summaries plus user-stated procedural constraints.

## Workbench

`/workbench` uses registered read/mutation boundaries rather than bypassing them.

Read-only operations such as workspace list/read and Git status/diff use `/v1/tools/read`, which refuses tools marked mutating.

Mutation path:

```text
UI action
  -> /v1/tools/propose (tool + exact arguments)
  -> short-lived approval id
  -> explicit confirmation
  -> /v1/tools/execute
  -> approval consumed once
  -> server executes stored tool + stored args
```

The client cannot replace arguments after approval. xterm displays fixed project-check output only and has stdin disabled.

### Concrete AI modes

- **Plan:** `/v1/agent/plan`; planner only.
- **Build:** bounded team run.
- **Fix:** bounded team run with a minimal/root-cause repair instruction.
- **Review:** read-only `/v1/chat` review of the actual current Git diff; no Builder call.

The project snapshot is deterministic UI metadata derived from the visible file tree, detected checks, and Git status; it does not spend model calls merely to say what project is open.

## Bounded team

`POST /v1/team/run` has at most four model calls:

```text
Architect -> [Researcher] -> Builder -> Reviewer -> STOP
```

Completed roles write artifacts/events. Reviewer approval means `awaiting_approval`, not automatic workspace mutation. Retry reconstructs the immutable `team_request` into a new task and records lineage.

## Installer setup bridge

The native Rust setup bridge owns only first-run configuration/recovery actions, not general machine authority.

### Hardware recommendation

A fixed internal Windows query reads total visible memory, system-drive free space, and GPU display name. No user/model text enters that command. RAM + disk choose a conservative curated-model recommendation; GPU name is informational only.

### Ollama

1. Detect `ollama.exe` and local API.
2. If missing, try fixed `winget` package install.
3. If that fails, download the official fixed Ollama installer URL.
4. Require valid Windows Authenticode status before executing fallback installer.
5. Start `ollama serve` with fixed argv if necessary.
6. Pull the selected validated model name and `nomic-embed-text`.
7. Final verifier queries `/api/tags` and requires both models.

### Cloud

OpenAI/Anthropic setup validates the exact selected model through each provider's retrieve-model endpoint. The secret is stored in the OS credential store; `setup.json` keeps only non-secret provider/model/workspace state. Tauri injects the secret only into the packaged sidecar process environment.

### Final verifier

The reusable native verifier checks Genesis-owned app-data writability, completed setup state, read access to the selected/starter workspace, and provider readiness. Normal desktop startup reuses the same verifier, turning `/setup` into a repair surface when saved configuration drifts.

## External workers

`EXTERNAL_WORKERS_JSON` is server-side only. Command workers use fixed argv with `create_subprocess_exec` and prompt/context on stdin. HTTP workers use explicit allowlisted endpoints. External workers execute only through approval-gated `worker.run`; direct `/v1/workers/run` accepts the bounded built-in team only.

## Research, voice, GitHub, MCP

- Researcher queries only configured SearXNG and preserves source IDs.
- Voice invokes only configured whisper.cpp binary/model with fixed transcription argv.
- GitHub credentials remain server-side; existing-file replacement is SHA-safe.
- MCP callers choose configured Streamable HTTP server names rather than arbitrary URLs; side-effect-capable calls require approval.

These are optional capabilities for the installed coding Workbench.

## Evolution

Evolution is evaluation infrastructure, not autonomous self-modification. Baseline/candidate cases are bounded and persisted. Deterministic gates must pass before explicit manual promotion. Promotion does not rewrite project files or runtime configuration.

## CI and release

The exact PR merge head must pass:

1. Python compile/pytest against real PostgreSQL + pgvector.
2. Embedded SQLite schema/vector-storage smoke.
3. Next.js production/static export.
4. PyInstaller Windows sidecar package.
5. Packaged sidecar launch using embedded SQLite, selected-provider system health, and Tauri-origin CORS.
6. Rust/Tauri native setup compile.
7. Actual NSIS installer build.
8. Silent NSIS installation smoke.

Tagged `v*` pushes build Windows bundles and publish them to GitHub Releases.

The repository does not claim the Genesis installer is Authenticode-signed without a real signing identity. Automatic update installation is intentionally deferred until a cryptographically verified signed-update path exists.

## Source-mode startup and diagnostics

Developers can still use `scripts/doctor.ps1`, `scripts/start.ps1`, Docker PostgreSQL/pgvector, and SearXNG. `/diagnostics` reports the active database backend, selected AI provider, Ollama, research, voice, GitHub, MCP, workers, scheduler, cognitive memory, and evolution without returning secret values.
