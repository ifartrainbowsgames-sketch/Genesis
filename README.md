# Genesis

Genesis is a **local-first personal AI workstation** for coding, chat, durable agent runs, cognitive memory, research, voice, and explicitly approved integrations.

## Genesis 0.10 — One-Click Genesis

The normal Windows path is now:

```text
Download Genesis setup.exe
        ↓
Run installer
        ↓
Genesis Setup opens as part of installation
        ↓
Choose Local AI or Cloud API
        ↓
Hardware/provider/model checks
        ↓
Choose an existing project or starter workspace
        ↓
Final native verification turns green
        ↓
Installer finishes
        ↓
Genesis opens directly in Workbench
```

A normal desktop user does **not** need to clone the repository, install Python/Node/Rust, run Docker, configure PostgreSQL, or use PowerShell to start Genesis.

### Local AI

Choose **Local with Ollama** and Genesis will:

1. inspect total RAM, free system-drive space, and GPU name;
2. recommend a conservative model for that PC;
3. detect an existing Ollama installation;
4. install Ollama automatically if it is missing;
5. prefer Windows Package Manager (`winget`) with fixed silent arguments;
6. if winget is unavailable/fails, download the official `OllamaSetup.exe`, require a valid Windows Authenticode signature, then run it silently;
7. start the local Ollama service when needed;
8. pull the selected chat model plus `nomic-embed-text`;
9. verify both models are actually installed before the installer can finish.

The curated 0.10 starter list is intentionally small: `qwen3:4b`, `qwen3:8b`, `gpt-oss:20b`, and `qwen3-coder:30b`. Hardware recommendations are conservative whole-system guidance, not promises about GPU offload or speed.

### Cloud AI

Choose **Cloud API** to configure OpenAI or Anthropic. Genesis validates both the credential **and access to the exact selected model** before setup completes. The API key is stored through the operating-system credential store; it is never written to `setup.json`.

The 0.10 wizard offers OpenAI GPT-5.6 Sol/Terra/Luna and Anthropic Claude Sonnet 5.

### Embedded desktop storage

The installed desktop application owns its durable runtime. It creates a private `genesis.db` SQLite database under the Genesis Windows application-data directory and starts the FastAPI sidecar with that database automatically.

Desktop SQLite stores:

- task/event history and replay artifacts;
- schedules;
- episodic memory;
- consolidated cognitive memory;
- evolution candidates/evaluations.

When local embeddings are available, SQLite stores vectors as JSON and Genesis performs a bounded in-process cosine ranking. Source/server deployments can continue using PostgreSQL + pgvector, where native vector distance queries and `FOR UPDATE SKIP LOCKED` schedule claiming remain enabled.

### Setup verification and repair

Before **Finish installation** becomes available, the native verifier checks:

- Genesis-owned app-data is writable;
- `setup.json` is complete;
- the selected project/starter workspace is readable;
- for Ollama: the service responds and both chat + embedding models are installed;
- for cloud: the validated credential is present in the Windows credential store.

The verifier does not write probe files into a user-selected project.

Normal desktop startup runs the same verification. If a configured installation later loses Ollama/models, a cloud credential, or workspace access, Genesis routes back into **First-run / Repair** instead of opening a knowingly broken Workbench.

### First desktop start

After setup, Genesis starts its packaged FastAPI sidecar with the embedded database, waits for local API health, and opens `/workbench` directly. Startup failures show repair/Diagnostics/retry actions rather than a half-ready editor.

Silent `/S` installs remain non-interactive and defer setup to first normal launch. Existing configured installations skip the interactive wizard during upgrades, then normal startup verification catches any runtime drift.

## Workbench

The Workbench is the default desktop surface:

- filtered workspace Explorer;
- Monaco code editor;
- Git status/diff;
- detected fixed build/test checks;
- output-only xterm (`stdin` disabled; not a shell);
- task and worker history;
- project snapshot with file types, branch, and detected checks;
- **Plan** — planner only, no Builder call;
- **Build** — bounded Architect → optional Researcher → Builder → Reviewer workflow;
- **Fix** — bounded minimal-repair team instruction;
- **Review** — read-only AI review of the actual current Git diff.

Generated changes remain proposals. File saves, project checks, external workers, GitHub writes, MCP calls, and other registered mutations continue through the explicit proposal → approval → single-use execution path.

## Core capabilities

- Tauri 2 Windows desktop shell
- packaged FastAPI sidecar
- Next.js + React workstation UI
- embedded SQLite desktop durability
- optional PostgreSQL + pgvector source/server backend
- Ollama plus optional OpenAI and Anthropic adapters
- streaming chat
- durable task/event ledger and replay
- bounded durable schedules
- episodic + cognitive memory
- shadow prompt evolution with deterministic evals and manual promotion
- source-tracked SearXNG research when configured
- local whisper.cpp speech-to-text when configured
- approval-gated GitHub, MCP, workspace mutations, project checks, and external workers

Genesis intentionally **does not self-deploy, self-copy, expose an unrestricted shell, auto-apply generated code, or auto-promote evolved behavior**.

## Optional services

The packaged desktop does not require these to open a functional coding Workbench:

- **SearXNG** — source-tracked web research
- **whisper.cpp** — local speech-to-text
- **GitHub token** — approved repository writes/PR operations
- **MCP configuration** — approved external MCP tools
- **external worker configuration** — approved allowlisted command/HTTP workers
- **PostgreSQL + pgvector** — optional source/server deployment backend; not required by the installed Windows desktop

Cloud-only AI installations can operate without Ollama. In that mode conversational memory remains durable; local vector embeddings are unavailable unless Ollama/embedding support is later configured, so memory search can fall back to text matching.

Use **Diagnostics** to see which capabilities are ready, unavailable, or intentionally unconfigured.

## Developer/source setup

Developers working on Genesis itself still use the repository workflow:

```powershell
Copy-Item .env.example .env
./scripts/setup.ps1
docker compose up -d postgres searxng
./scripts/doctor.ps1
./scripts/start.ps1
```

Local source-mode URLs:

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

## Workspace boundary

Genesis touches only the selected workspace. In source mode you can point it at another repository you own:

```powershell
./scripts/use-workspace.ps1 -Path "C:/Code/my-project"
```

The in-app selector stays inside configured roots. Recursive Explorer scans omit `.git`, `node_modules`, `.next`, virtual environments, build output, Rust `target`, and cache trees.

## Durable runtime

A bounded team run stores the immutable request, Architect plan, optional Researcher report, Builder change proposal, Reviewer report, ordered events, final status, and stop reason. Retries reconstruct the original request and record lineage instead of mutating the previous run.

On PostgreSQL, schedule claiming uses database row locking with `SKIP LOCKED`. On the single-sidecar SQLite desktop backend, Genesis uses an in-process claim lock and still advances `next_run_at` before execution so the scheduler loop and manual run-due action cannot duplicate the same job.

## External workers

External runtimes are optional and server-side allowlisted through `EXTERNAL_WORKERS_JSON`. Command workers use a fixed argv array, receive the task on stdin, stay inside the selected workspace, and launch without a shell. HTTP workers use explicit HTTP(S) endpoints. External workers execute only through the approval-gated `worker.run` tool.

## Cognitive memory

Genesis preserves raw episodic records and stores consolidated semantic/procedural knowledge separately. Consolidated items retain source-record IDs and confidence. PostgreSQL uses pgvector for vector ranking; desktop SQLite uses bounded in-process cosine ranking when embeddings exist. Consolidation never rewrites or deletes the source episodes.

## Shadow evolution

Evolution remains shadow-first. Genesis evaluates a baseline and a bounded set of prompt candidates against deterministic cases. A candidate can be promoted only after required gates pass and a human explicitly approves it. Promotion does not autonomously rewrite source code.

## Desktop build

Development desktop build:

```powershell
npm run desktop:dev:windows
```

Create the Windows NSIS installer:

```powershell
npm run desktop:build:windows
```

Tauri bundles the PyInstaller FastAPI sidecar. The Windows bundle target is NSIS and uses the Genesis installer-setup hook.

## Testing and CI

Pull requests must pass three primary gates:

- **server** — Python compile + pytest against real `pgvector/pgvector:pg16`, plus an embedded SQLite schema/vector-storage smoke test;
- **web** — Next.js production/static-export build;
- **desktop-sidecar** — packaged FastAPI sidecar using embedded SQLite, system-health/provider/CORS checks, Rust/Tauri compile, **actual NSIS installer build**, and silent NSIS install smoke test.

A `v*` tag runs `.github/workflows/release.yml`, builds the Windows bundle, uploads the workflow artifact, and publishes it to a GitHub Release.

The repository does not claim an installer or update is Authenticode-signed unless a real signing identity/certificate has been supplied to the release environment. Automatic self-update installation is intentionally not enabled until a signed update-verification path is available.

## Security model

- Local API binds to loopback by default.
- Desktop durable data is stored under Genesis application data; setup write probes do not touch the selected project.
- Workspace paths cannot escape the selected root.
- Mutating tools use short-lived single-use approval IDs.
- Execution uses the exact tool arguments stored at approval time.
- Generated code is previewed and not auto-applied.
- Built-in project checks are allowlisted; there is no unrestricted shell tool.
- Workbench xterm is output-only.
- External workers are server-side allowlisted and approval-gated.
- GitHub existing-file writes are SHA-safe.
- MCP destinations are allowlisted and calls require approval.
- Installer cloud keys are stored through the OS credential store.
- Ollama fallback download must have a valid Windows Authenticode signature before Genesis executes it.
- Hardware inspection uses a fixed internal Windows query; user text is never interpolated into a shell command.
- Team calls and schedules stay bounded.
- Evolution stays shadow-first and manual-promotion-only.

See `SECURITY.md`, `docs/ARCHITECTURE.md`, and `PROJECT_STATUS.md` for detailed boundaries and roadmap status.
