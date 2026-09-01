# Genesis

Genesis is a **local-first personal AI workspace**. It gives you one interface for local models and optional cloud models, searchable long-term memory, and an agent planner whose tool actions require explicit user approval.

This starter intentionally **does not self-deploy, self-copy, or execute unrestricted shell commands**. The agent can propose actions, but file-changing tools only run after approval and are sandboxed to `./workspace`.

## What works in this starter

- FastAPI backend
- Next.js 16.3.3 + React 19.2.7 web UI
- Ollama chat support
- Optional OpenAI Responses API and Anthropic Messages API adapters
- PostgreSQL + pgvector conversation memory with inspect/search/delete UI
- Streaming chat for local and optional cloud providers
- Agent task planner
- Bounded Architect → Builder → Reviewer team with a persistent task ledger
- Approval-gated workspace tools: list/read/write/mkdir/apply changes
- In-app repository selector limited to configured folders
- Git status/diff and restricted build/test runner
- Tauri 2 desktop shell scaffold
- Windows PowerShell bootstrap scripts
- Docker Compose for PostgreSQL + pgvector

## 1. Prerequisites

Recommended on Windows:

- Python 3.11+
- Node.js 22+
- Docker Desktop (for PostgreSQL)
- Rust toolchain only if you want the Tauri desktop app
- Ollama installed natively for best GPU access

Pull two local models after installing Ollama:

```powershell
ollama pull qwen3:8b
ollama pull nomic-embed-text
```

You can choose different model names in `.env`.

## 2. Quick start on Windows

```powershell
Copy-Item .env.example .env
./scripts/setup.ps1
./scripts/start.ps1
```

Then open:

- Web UI: http://localhost:3000
- API docs: http://localhost:8000/docs

## 3. Start PostgreSQL

```powershell
docker compose up -d postgres
```

If you do not have Docker yet, install Docker Desktop or point `DATABASE_URL` to an existing PostgreSQL instance with the `vector` extension.

## Point Genesis at an existing code repository

By default, Genesis can only touch `./workspace`. On Windows you can point it at a repository you own:

```powershell
./scripts/use-workspace.ps1 -Path "C:/Code/my-project"
```

The script also sets `WORKSPACE_ALLOWED_ROOTS` to the repository parent, so the in-app selector can switch between sibling repositories. Every tool resolves against the selected root and rejects path traversal. Restart the API after changing `.env`.

## 4. Optional cloud models

Add API keys to `.env` only if you want cloud fallback:

```env
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
```

The UI lets you choose `ollama`, `openai`, or `anthropic` per request.

## 5. Architecture

```text
Browser / desktop shell later
        |
        v
Next.js UI :3000
        |
        v
FastAPI :8000
  |        |         |
  |        |         +--> Approval-gated workspace tools
  |        +------------> Memory service -> PostgreSQL/pgvector
  +---------------------> Model router -> Ollama / OpenAI / Anthropic
```

See `docs/ARCHITECTURE.md` for the next build phases.

## Security model

- Workspace tools cannot escape the configured workspace root.
- Writes have a size limit.
- Tool execution requires a short-lived approval ID plus an explicit `approved: true` request.
- No unrestricted shell tool is enabled in this starter.
- Cloud providers are opt-in.

## Current workstation features

- bounded Architect → Builder → Reviewer workflow with 1–3 call budget
- persistent task ledger and reviewer findings
- streaming responses
- repository selection inside configured roots
- Git status/diff
- restricted build/test checks
- exact multi-file preview + approval
- inspectable/searchable/deletable memory
- activity timeline

## Next build targets

1. GitHub adapter inside Genesis
2. MCP client/server registry
3. Researcher role with source-tracked research broker
4. Desktop sidecar packaging
5. Voice input/output

## Desktop shell

After the API is running and Rust is installed:

```powershell
npm run desktop:dev
```

The Tauri shell starts the Next.js dev UI automatically. The FastAPI service still runs separately in this starter; bundling it as a signed sidecar is a later phase.
