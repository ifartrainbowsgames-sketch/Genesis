# Genesis

Genesis is a **local-first personal AI workstation** for chat, coding, research, voice, durable agent runs, cognitive memory, and explicitly approved integrations. Ollama is the default model provider; OpenAI and Anthropic remain optional adapters.

Genesis 0.9 adds the real Workbench and durable operating layer: Monaco editing, an output-only xterm check console, task replay/event history, schedules, allowlisted external workers, cognitive memory consolidation, shadow prompt evolution, PostgreSQL/pgvector integration CI, Doctor diagnostics, and tagged Windows bundle artifacts.

Genesis intentionally **does not self-deploy, self-copy, expose an unrestricted shell, auto-apply generated code, or auto-promote evolved behavior**.

## What works now

- FastAPI backend
- Next.js 16 + React 19 workstation UI
- Ollama chat plus optional OpenAI and Anthropic adapters
- PostgreSQL + pgvector episodic and cognitive memory
- Streaming chat with episodic + consolidated knowledge retrieval
- Bounded Architect → optional Researcher → Builder → Reviewer workflow
- Persistent task ledger, immutable request artifacts, ordered run events, and retries
- Durable bounded interval schedules
- Workbench with filtered Explorer, Monaco editor, Git diff/status, tasks/workers, and output-only xterm
- Approval-gated local writes, fixed project checks, GitHub writes, MCP calls, and external workers
- Fixed-argv command worker adapter (`shell=False`) and allowlisted HTTP worker adapter
- Repository selector restricted to configured roots
- GitHub adapter with SHA-safe replacement
- MCP v2 Streamable HTTP allowlist
- Source-tracked Researcher backed by local SearXNG
- Local push-to-talk speech-to-text through configured whisper.cpp
- Shadow prompt evolution with deterministic eval gates and manual promotion only
- Doctor diagnostics in the UI and `scripts/doctor.ps1`
- Tauri 2 desktop shell with PyInstaller FastAPI sidecar
- PostgreSQL/pgvector CI integration plus Windows sidecar/Tauri gates
- Tag-triggered Windows bundle artifact workflow

## 1. Windows prerequisites

Recommended:

- Python 3.11+
- Node.js 22+
- Docker Desktop
- Ollama
- Git
- Rust stable when building the desktop application
- whisper.cpp only if you want local speech-to-text

Pull the default local models:

```powershell
ollama pull qwen3:8b
ollama pull nomic-embed-text
```

## 2. First setup

```powershell
Copy-Item .env.example .env
./scripts/setup.ps1
docker compose up -d postgres searxng
./scripts/doctor.ps1
./scripts/start.ps1
```

Open:

- Workstation: `http://localhost:3000`
- Workbench: `http://localhost:3000/workbench`
- Runtime: `http://localhost:3000/runtime`
- Memory: `http://localhost:3000/memory`
- Evolution: `http://localhost:3000/evolution`
- Research: `http://localhost:3000/research`
- Voice: `http://localhost:3000/voice`
- Connections: `http://localhost:3000/connections`
- Diagnostics: `http://localhost:3000/diagnostics`
- API docs: `http://localhost:8000/docs`

`./scripts/doctor.ps1` checks developer prerequisites, `.env`, the Python environment, web dependencies, Docker Compose parsing, and—when the API is running—the live `/v1/system/health` component report.

## 3. Use an existing local repository

Genesis touches only the selected workspace. Point it at a repository you own:

```powershell
./scripts/use-workspace.ps1 -Path "C:/Code/my-project"
```

The script updates `WORKSPACE_ROOT` and adds the repository parent to `WORKSPACE_ALLOWED_ROOTS`. The in-app repository picker can switch only inside configured roots.

The Workbench Explorer also skips `.git`, `node_modules`, `.next`, virtual environments, build output, Rust `target`, and cache trees so generated/dependency files do not crowd out source files.

## 4. Workbench

`/workbench` is the coding surface:

- Explorer reads the selected workspace through the read-only tool broker.
- Monaco opens UTF-8 source files.
- Save creates an exact `workspace.write` proposal, shows a browser confirmation, then consumes a single-use approval token.
- Detected project checks remain restricted to six fixed command families: Python compile/test, npm build/test, and Cargo check/test.
- xterm is **output-only** (`stdin` disabled); it displays restricted check output and is not a shell.
- Git status/diff is read-only and degrades gracefully when the selected workspace is not a Git repository.

## 5. Durable runtime

`/runtime` exposes the persistent operating layer.

A team run stores:

- the immutable `team_request`
- Architect plan
- optional Researcher report
- Builder change proposal
- Reviewer report
- ordered `RunEvent` history
- final status and stop reason

A retry reconstructs the original request artifact and records `retry_of` lineage rather than silently mutating the old run.

Durable schedules are stored in PostgreSQL. Due rows are claimed with `FOR UPDATE SKIP LOCKED`; `next_run_at` advances before execution so a slow run is not picked up twice. Scheduled runs use the same bounded team and still stop before workspace mutation.

## 6. External workers

External runtimes are optional and **server-side allowlisted** through `EXTERNAL_WORKERS_JSON`.

Command workers use a fixed argv array, receive the prompt on stdin, remain inside the selected workspace, and launch through `asyncio.create_subprocess_exec` without a shell. HTTP workers use an explicitly configured HTTP(S) endpoint and optional bearer token environment-variable name.

Example shapes:

```env
EXTERNAL_WORKERS_JSON=[{"name":"agent-cli","type":"command","argv":["agent-cli","--print"],"cwd":".","enabled":true}]
```

or:

```env
EXTERNAL_WORKERS_JSON=[{"name":"openhands","type":"http","url":"http://127.0.0.1:3100/run","enabled":true}]
```

The direct `/v1/workers/run` endpoint accepts the built-in `genesis-team` only. External workers execute through the registered `worker.run` tool, so they require proposal → explicit approval → single-use execution just like other side-effect-capable tools.

This generic adapter can wrap products such as Claude Code, Codex, OpenHands, Wayland, or another local worker when you explicitly configure a compatible fixed command or HTTP bridge. Genesis does not auto-discover arbitrary executables.

## 7. Cognitive memory

Genesis keeps raw episodic `MemoryRecord` rows unchanged and stores consolidated knowledge in a separate `MemoryKnowledge` table.

The V1 consolidator creates:

- semantic conversation summaries
- procedural/user-stated working preferences and constraints
- source record IDs for traceability
- confidence values
- optional pgvector embeddings

`/memory` shows episodic and cognitive layers separately, supports search, and lets the user trigger consolidation. Chat retrieval can use both layers. Consolidation does not delete the source episodes.

## 8. Shadow evolution

`/evolution` implements bounded prompt evolution rather than live self-modification.

Each experiment:

1. evaluates the baseline prompt on 1–10 deterministic cases;
2. asks the selected provider for at most three bounded variants;
3. runs the same cases against each variant;
4. scores required substrings and forbidden substrings deterministically;
5. stores candidate score, baseline score, case results, latency, provider, and model;
6. leaves every candidate in `shadow` status.

A candidate can be promoted only after explicit user confirmation **and** only when every deterministic case passed and its score met or beat baseline. There is no automatic promotion or code rewrite. An older passing candidate can be promoted again, providing a manual rollback path.

## 9. Source-tracked research

Start the bundled SearXNG broker:

```powershell
docker compose up -d searxng
```

The Researcher receives bounded result titles, URLs, and snippets and produces a synthesis with source IDs such as `[S1]`. A standalone research run is stored as a task artifact, and a team run can use the same source-tracked artifact as Builder context.

## 10. Local voice

Genesis does not send microphone audio to a cloud speech service by default. The browser records mono audio, converts it to 16 kHz PCM WAV, and sends it to FastAPI. The backend invokes only the configured whisper.cpp binary/model with a fixed transcription argument set.

```env
WHISPER_CPP_BINARY=C:/Tools/whisper.cpp/build/bin/Release/whisper-cli.exe
WHISPER_CPP_MODEL=C:/Tools/whisper.cpp/models/ggml-base.en.bin
```

The transcript is inspectable/editable before sending it to chat. Spoken replies use browser/OS speech synthesis and can be disabled.

## 11. GitHub and MCP

GitHub:

```env
GITHUB_TOKEN=...
GITHUB_API_URL=https://api.github.com
```

Use a fine-grained token restricted to repositories and permissions you actually want. Existing-file replacement requires the SHA Genesis observed during read; stale writes are rejected.

MCP:

```env
MCP_SERVERS_JSON=[{"name":"local-tools","url":"http://127.0.0.1:9000/mcp","enabled":true}]
```

Genesis connects only to explicitly configured Streamable HTTP endpoints. `mcp.call_tool` is treated as side-effect-capable and goes through approval.

## 12. Desktop application

Development with packaged FastAPI sidecar:

```powershell
npm run desktop:dev:windows
```

Bundle build:

```powershell
npm run desktop:build:windows
```

The PyInstaller sidecar is named for the Rust target triple and launched by Tauri. PostgreSQL, Ollama, SearXNG, and whisper.cpp remain explicit local services/adapters rather than being silently embedded.

Tagged pushes matching `v*` run `.github/workflows/release.yml` and upload Windows bundle artifacts. These artifacts are not claimed to be Authenticode-signed unless a real signing identity/certificate is supplied to the release environment.

## Testing and CI

Pull requests run three primary gates:

- **server** — Python compile + pytest against a real `pgvector/pgvector:pg16` PostgreSQL service
- **web** — Next.js production/static-export build
- **desktop-sidecar** — Windows PyInstaller sidecar package + Rust/Tauri compile check

The server suite covers authority boundaries, workspace traversal, approval single-use/expiry, planner parsing, Ollama embedding fallback, restricted project execution, GitHub SHA-safe writes, MCP validation, research source hygiene, external-worker safety, deterministic evolution scoring, cognitive-memory extraction, and PostgreSQL-backed runtime integration.

## Architecture

```text
Next.js / Tauri workstation
  |-- Workbench (Explorer / Monaco / diff / output-only xterm)
  |-- Runtime (tasks / events / retries / schedules / workers)
  |-- Memory (episodic + cognitive)
  |-- Evolution (shadow candidates + deterministic eval)
  |-- Research / Voice / Connections / Diagnostics
  v
FastAPI sidecar :8000
  |-- model router ----------> Ollama / optional OpenAI / Anthropic
  |-- durable runtime -------> PostgreSQL
  |-- episodic/cognitive ----> PostgreSQL + pgvector
  |-- safe workspace --------> selected local root
  |-- tool approval broker --> short-lived single-use approvals
  |-- external workers ------> fixed argv or allowlisted HTTP
  |-- GitHub / MCP ----------> explicit adapters
  |-- Researcher ------------> SearXNG
  `-- voice STT -------------> configured whisper.cpp
```

See `docs/ARCHITECTURE.md` and `PROJECT_STATUS.md` for detailed flows and remaining release constraints.

## Security model

- Workspace paths cannot escape the selected root.
- Writes have configured size limits.
- Recursive Explorer scans omit dependency/build/cache trees.
- Mutating registered tools use short-lived single-use approval IDs.
- Generated code is previewed and not auto-applied.
- Project checks are allowlisted instead of exposing a shell.
- xterm is output-only.
- External command workers use fixed argv + `shell=False` and are approval-gated.
- External HTTP workers are explicit allowlist entries and are approval-gated.
- GitHub credentials remain server-side; existing-file writes are SHA-safe.
- MCP destinations are allowlisted and calls require approval.
- Research routes through configured SearXNG.
- Voice invokes only configured whisper.cpp paths and bounded WAV input.
- Team calls and schedules remain bounded.
- Evolution stays shadow-first and manual-promotion-only.
- Cloud model providers are opt-in.

See `SECURITY.md` for the threat boundaries and responsible reporting guidance.
