# Genesis

Genesis is a **local-first personal AI workstation** for coding, chat, research, voice, durable agent runs, cognitive memory, and explicitly approved integrations.

## Genesis 0.10 — One-Click Genesis

For a normal Windows user, the intended path is now:

```text
Download Genesis setup.exe
        ↓
Run installer
        ↓
Genesis Setup opens inside installation
        ↓
Choose Local AI or Cloud API
        ↓
Genesis installs / validates the AI provider
        ↓
Setup checks turn green
        ↓
Installer finishes and Genesis opens directly in Workbench
```

There is no repository clone, Python environment, Node setup, Docker command, or PowerShell requirement for the **core desktop Workbench**.

### Local AI

Choose **Local with Ollama** and Genesis will:

1. detect an existing Ollama installation;
2. install Ollama automatically if it is missing;
3. prefer Windows Package Manager (`winget`) with fixed silent arguments;
4. if winget is unavailable/fails, download the official `OllamaSetup.exe`, require a valid Windows Authenticode signature, then run it silently;
5. start the local Ollama service if necessary;
6. let you choose a curated chat/coding model;
7. pull that model plus `nomic-embed-text` for local memory embeddings;
8. persist only the selected provider/model settings.

### Cloud AI

Choose **Cloud API** to configure OpenAI or Anthropic. Genesis validates the API key before setup can complete. The secret is stored through the operating-system credential store; it is **not** written to `setup.json` or committed configuration files.

### First desktop start

After setup, Genesis waits for its local FastAPI sidecar to become healthy and then opens `/workbench` directly. If startup fails, Genesis shows a recovery screen with Diagnostics/retry instead of opening a half-ready editor.

Interactive upgrades skip the setup wizard when an installation is already configured. Silent `/S` installs stay fully non-interactive; the setup wizard resumes on first normal launch.

## What the Workbench does

- Filtered workspace Explorer
- Monaco code editor
- Git status and diff
- Restricted build/test checks
- Output-only xterm check console (`stdin` disabled)
- Task and worker history
- **Ask Genesis** task box that uses the AI provider selected during installation
- Architect → optional Researcher → Builder → Reviewer bounded team
- Generated changes are proposals; they are never applied automatically
- Saves and other mutations remain approval-gated

## Core capabilities

- FastAPI local sidecar
- Next.js + React workstation UI
- Tauri 2 Windows desktop shell
- Ollama plus optional OpenAI and Anthropic model adapters
- PostgreSQL + pgvector episodic/cognitive memory when configured
- Streaming chat
- Durable task/event ledger and replay
- Bounded PostgreSQL schedules
- Cognitive-memory consolidation
- Shadow prompt evolution with deterministic evals and manual promotion
- Source-tracked SearXNG research when configured
- Local whisper.cpp speech-to-text when configured
- Approval-gated GitHub, MCP, workspace mutations, project checks, and external workers

Genesis intentionally **does not self-deploy, self-copy, expose an unrestricted shell, auto-apply generated code, or auto-promote evolved behavior**.

## Optional services

The packaged desktop can open and use its configured AI provider without PostgreSQL, SearXNG, or whisper.cpp. Features degrade explicitly when those optional services are unavailable:

- PostgreSQL/pgvector — durable episodic/cognitive memory, tasks, schedules, evolution history
- SearXNG — source-tracked web research
- whisper.cpp — local speech-to-text
- GitHub token — repository writes/PR operations
- MCP configuration — approved external MCP tools

Use **Diagnostics** inside Genesis to see which capabilities are ready, unavailable, or intentionally unconfigured.

## Developer setup

Developers working on Genesis from source still use the repository workflow:

```powershell
Copy-Item .env.example .env
./scripts/setup.ps1
docker compose up -d postgres searxng
./scripts/doctor.ps1
./scripts/start.ps1
```

Local URLs in source/developer mode:

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

## Use another repository

Genesis touches only the selected workspace. In source mode you can point it at a repository you own:

```powershell
./scripts/use-workspace.ps1 -Path "C:/Code/my-project"
```

The repository selector can switch only inside configured roots. Recursive Workbench scans omit `.git`, `node_modules`, `.next`, virtual environments, build output, Rust `target`, and cache trees.

## Durable runtime

A bounded team run stores:

- immutable `team_request`
- Architect plan
- optional Researcher report
- Builder change proposal
- Reviewer report
- ordered run events
- final status and stop reason

Retries reconstruct the original request and record lineage instead of mutating the previous run. Durable schedules use the same bounded team and still stop before workspace mutation.

## External workers

External runtimes are optional and server-side allowlisted through `EXTERNAL_WORKERS_JSON`.

Command workers use a fixed argv array, receive the task on stdin, stay inside the selected workspace, and launch without a shell. HTTP workers use explicit HTTP(S) endpoints. External workers execute only through the approval-gated `worker.run` tool.

## Cognitive memory

Genesis preserves raw episodic records and stores consolidated semantic/procedural knowledge separately. Consolidated items retain source-record IDs, confidence, and optional pgvector embeddings. The original episodes are not rewritten or deleted by consolidation.

## Shadow evolution

Evolution remains shadow-first. Genesis evaluates a baseline and a small bounded set of prompt candidates against deterministic cases. A candidate can be promoted only after every required gate passes and a human explicitly approves it. Promotion does not autonomously rewrite source code.

## Desktop build

Development desktop build:

```powershell
npm run desktop:dev:windows
```

Create the Windows NSIS installer:

```powershell
npm run desktop:build:windows
```

Tauri bundles the PyInstaller FastAPI sidecar. The Windows bundle target is NSIS and uses the Genesis post-install setup hook.

## Testing and CI

Pull requests have three primary gates:

- **server** — Python compile + pytest against a real `pgvector/pgvector:pg16` PostgreSQL service
- **web** — Next.js production/static-export build
- **desktop-sidecar** — packaged FastAPI sidecar health/CORS test, Rust/Tauri compile, **actual NSIS installer build**, and silent NSIS install smoke test

A `v*` tag runs `.github/workflows/release.yml`, builds the Windows bundle, uploads the workflow artifact, and publishes it to a GitHub Release.

The repository does not claim an installer is Authenticode-signed unless a real signing identity/certificate has been supplied to the release environment.

## Security model

- Local API binds to loopback by default.
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
- Team calls and schedules stay bounded.
- Evolution stays shadow-first and manual-promotion-only.

See `SECURITY.md`, `docs/ARCHITECTURE.md`, and `PROJECT_STATUS.md` for the detailed boundaries and roadmap status.
