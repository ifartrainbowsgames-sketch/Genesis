# Genesis

Genesis is a **local-first personal AI workstation** for chat, coding, research, voice, memory, and explicit tool integrations. Local Ollama models are the default; OpenAI and Anthropic remain optional adapters.

Genesis intentionally **does not self-deploy, self-copy, or expose unrestricted shell execution**. Coding changes, GitHub writes, and MCP calls remain bounded, inspectable, and user-controlled.

## What works now

- FastAPI backend
- Next.js 16.3.3 + React 19.2.7 workstation UI
- Ollama chat plus optional OpenAI Responses API and Anthropic Messages API adapters
- PostgreSQL + pgvector memory with inspect/search/delete controls
- Streaming chat
- Bounded Architect → optional Researcher → Builder → Reviewer workflow
- Persistent task ledger and artifact handoffs
- Exact multi-file proposal preview before apply
- Approval-gated workspace tools, Git operations, GitHub operations, and MCP calls
- Repository selector restricted to configured local roots
- Restricted project build/test runner
- GitHub repository/file/branch/pull-request adapter with SHA-safe replacement
- MCP Python SDK v2 client with an allowlisted Streamable HTTP registry
- Source-tracked Researcher backed by a local SearXNG broker
- Local push-to-talk speech-to-text through a configured whisper.cpp executable/model
- Optional operating-system speech synthesis for spoken replies
- Tauri 2 desktop shell with a PyInstaller-packaged FastAPI sidecar build path
- Windows setup and build scripts

## 1. Windows prerequisites

Recommended:

- Python 3.11+
- Node.js 22+
- Docker Desktop
- Ollama
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
./scripts/start.ps1
```

Open:

- Workstation: http://localhost:3000
- Researcher: http://localhost:3000/research
- Voice: http://localhost:3000/voice
- Connections: http://localhost:3000/connections
- API docs: http://localhost:8000/docs

SearXNG is local by default on `http://127.0.0.1:8080`. Its JSON search output is used as a source broker; the Researcher receives result titles, URLs, and snippets and produces a synthesis with source IDs such as `[S1]`.

## 3. Use an existing local repository

Genesis touches only the selected workspace. Point it at a repository you own:

```powershell
./scripts/use-workspace.ps1 -Path "C:/Code/my-project"
```

The script updates `WORKSPACE_ROOT` and adds the repository parent to `WORKSPACE_ALLOWED_ROOTS`, allowing the in-app repository picker to switch only within configured roots. Local file, Git, Builder-context, and restricted project-check paths are resolved against that selected root.

## 4. Optional cloud models

Add only the providers you want:

```env
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
```

The provider selector remains per request, so local Ollama can stay the default.

## 5. Source-tracked research

Start the bundled broker:

```powershell
docker compose up -d searxng
```

Default `.env` values:

```env
SEARXNG_URL=http://127.0.0.1:8080
RESEARCH_TIMEOUT_SECONDS=20
RESEARCH_MAX_RESULTS=12
```

The standalone `/research` workspace stores each completed report as a task-ledger artifact. Team runs can also insert an optional Researcher step before Builder. The bounded team budget is 1–4 model calls, so enabling Researcher still cannot create recursive agent loops.

## 6. Local voice

Genesis does not send microphone audio to a cloud speech service by default. The browser records mono audio, converts it to 16 kHz PCM WAV, and sends it to the local FastAPI endpoint. The backend then invokes only the configured whisper.cpp CLI binary with fixed transcription arguments.

Set these paths in `.env`:

```env
WHISPER_CPP_BINARY=C:/Tools/whisper.cpp/build/bin/Release/whisper-cli.exe
WHISPER_CPP_MODEL=C:/Tools/whisper.cpp/models/ggml-base.en.bin
```

Then open `/voice`. You can inspect/edit the transcript before sending it to Genesis. Spoken assistant replies use the browser/operating system speech-synthesis voices and can be disabled.

## 7. GitHub connection

Use a fine-grained token restricted to repositories and permissions you actually want Genesis to use:

```env
GITHUB_TOKEN=...
GITHUB_API_URL=https://api.github.com
```

The `/connections` workspace can inspect repositories, read files, create branches, create/replace files, and open pull requests. Replacing an existing remote file requires the SHA observed during the read; a stale SHA causes the update to be rejected rather than silently overwriting a newer version.

## 8. MCP connections

Genesis only connects to explicitly configured Streamable HTTP MCP endpoints:

```env
MCP_SERVERS_JSON=[{"name":"local-tools","url":"http://127.0.0.1:9000/mcp","enabled":true}]
```

In `/connections`, Genesis can list configured servers, discover advertised tool schemas, and call an advertised tool after approval. Arbitrary stdio command launch is intentionally not exposed by this registry.

## 9. Desktop application

The Tauri shell can package the FastAPI backend as an external sidecar. On Windows:

```powershell
npm run desktop:dev:windows
```

That command builds `genesis-server` with PyInstaller, places the target-triple binary in Tauri's sidecar directory, and launches the desktop development app.

Build the desktop bundle with:

```powershell
npm run desktop:build:windows
```

The sidecar removes the need to manually start FastAPI for the packaged desktop app. PostgreSQL, Ollama, SearXNG, and whisper.cpp are still explicit local dependencies/adapters rather than being silently embedded. Installer signing and a fully self-contained dependency bootstrap are later release-hardening work.

## Architecture

```text
Next.js / Tauri workstation
      |     |      |
      |     |      +--> Research / Voice / Connections
      |     v
      +--> FastAPI sidecar :8000
              |
      +-------+----------+-----------+-----------+
      |                  |           |           |
  model router         memory     tool broker  research
      |                  |        /   |   \       |
 Ollama/cloud         pgvector workspace GitHub MCP SearXNG
                                      |
                                explicit approval
```

See `docs/ARCHITECTURE.md` for the detailed flows.

## Security model

- Local workspace tools cannot escape the selected workspace root.
- Writes have a configured size limit.
- Tool executions use short-lived, single-use approval IDs.
- Generated code is shown before application.
- Project checks are allowlisted instead of providing a general shell.
- GitHub credentials stay server-side and can be restricted with fine-grained tokens.
- Existing GitHub-file updates use SHA-safe replacement.
- MCP server destinations come only from `MCP_SERVERS_JSON`.
- MCP calls are treated as side-effect-capable and require approval.
- Research requests go only through the configured SearXNG broker.
- Voice transcription invokes only the configured whisper.cpp binary/model and accepts WAV input with size limits.
- Cloud model providers are opt-in.

## Current build direction

The core workstation, Researcher, voice path, GitHub/MCP integrations, and desktop sidecar path are implemented. The next release-hardening work is desktop installer signing, local dependency health/setup UX, richer MCP authentication profiles, artifact/task drill-down, and automated integration tests for research/voice services.
