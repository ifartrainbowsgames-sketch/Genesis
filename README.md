# Genesis

Genesis is a **local-first personal AI workspace**. It gives you one interface for local models and optional cloud models, searchable long-term memory, bounded AI coding roles, and approval-gated tools.

Genesis intentionally **does not self-deploy, self-copy, or execute unrestricted shell commands**. Agents can propose actions, but file-changing and external tool actions are bounded and remain under user control.

## What works now

- FastAPI backend
- Next.js 16.3.3 + React 19.2.7 web UI
- Ollama chat support
- Optional OpenAI Responses API and Anthropic Messages API adapters
- PostgreSQL + pgvector conversation memory with inspect/search/delete UI
- Streaming chat for local and optional cloud providers
- Bounded Architect → Builder → Reviewer team with a persistent task ledger
- Approval-gated workspace tools: list/read/write/mkdir/apply changes
- In-app repository selector limited to configured folders
- Git status/diff and restricted build/test runner
- Approval-gated GitHub repository/file/branch/pull-request tools
- MCP Python SDK v2 client using allowlisted Streamable HTTP servers
- MCP tool discovery and approval-gated tool calls
- Connections control center at `/connections`
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

## 2. Quick start on Windows

```powershell
Copy-Item .env.example .env
./scripts/setup.ps1
docker compose up -d postgres
./scripts/start.ps1
```

Then open:

- Workstation: http://localhost:3000
- Connections: http://localhost:3000/connections
- API docs: http://localhost:8000/docs

## 3. Point Genesis at an existing code repository

By default, Genesis can only touch `./workspace`. On Windows you can point it at a repository you own:

```powershell
./scripts/use-workspace.ps1 -Path "C:/Code/my-project"
```

The script also sets `WORKSPACE_ALLOWED_ROOTS` to the repository parent, so the in-app selector can switch between sibling repositories. Every local file, Git, and restricted build tool resolves against the selected root and rejects path traversal.

## 4. Optional cloud models

Add API keys to `.env` only if you want cloud fallback:

```env
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
```

The UI lets you choose `ollama`, `openai`, or `anthropic` per request.

## 5. GitHub connection

Create a fine-grained GitHub token with access only to the repositories and operations you want Genesis to use, then add it to `.env`:

```env
GITHUB_TOKEN=...
GITHUB_API_URL=https://api.github.com
```

Genesis can inspect repositories, list/read files, create a branch, safely create/replace a file, and open a pull request. Replacing an existing remote file requires the SHA observed during the read, so Genesis refuses a stale overwrite if the file changed in the meantime.

## 6. MCP connections

Genesis uses the current MCP Python SDK v2 and only connects to explicitly configured Streamable HTTP endpoints. Configure them in `.env`:

```env
MCP_SERVERS_JSON=[{"name":"local-tools","url":"http://127.0.0.1:9000/mcp","enabled":true}]
```

Then open `/connections`, refresh configured servers, discover the advertised tools, inspect the input schema, enter exact JSON arguments, and approve the call. Arbitrary stdio commands are intentionally not enabled by this registry.

## 7. Architecture

```text
Next.js workstation / connections UI
                |
                v
           FastAPI :8000
      /          |           \
     v           v            v
Model router   Memory       Tool broker
     |           |          /    |     \
Ollama/cloud  pgvector  workspace GitHub MCP
```

See `docs/ARCHITECTURE.md` for the detailed flow.

## Security model

- Workspace tools cannot escape the selected workspace root.
- Writes have a size limit.
- Tool execution uses short-lived single-use approval IDs.
- Generated code is previewed before application.
- Restricted build/test commands are allowlisted rather than arbitrary shell commands.
- GitHub tokens stay server-side and can be fine-grained to selected repositories.
- Existing GitHub files use SHA-safe replacement checks.
- MCP endpoints must be present in `MCP_SERVERS_JSON`; arbitrary runtime URLs are rejected.
- MCP tool calls are treated as mutating/side-effect-capable actions and require an approved tool execution.
- Cloud model providers are opt-in.

## Current workstation features

- bounded Architect → Builder → Reviewer workflow with a 1–3 call budget
- persistent task ledger and reviewer findings
- streaming responses
- repository selection inside configured roots
- Git status/diff
- restricted build/test checks
- exact multi-file preview + approval
- inspectable/searchable/deletable memory
- activity timeline
- GitHub + MCP Connections control center

## Next build targets

1. Researcher role with a source-tracked web research broker
2. Desktop sidecar packaging for the FastAPI service
3. Voice input/output
4. Richer MCP authentication profiles and connection health checks
5. Artifact memory and task-ledger drill-down

## Desktop shell

After the API is running and Rust is installed:

```powershell
npm run desktop:dev
```

The Tauri shell starts the Next.js dev UI automatically. The FastAPI service still runs separately; bundling it as a signed sidecar is a later phase.
