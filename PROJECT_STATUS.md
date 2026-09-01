# Genesis project status

## Phase 1 — foundation: DONE

- [x] Monorepo layout
- [x] FastAPI API
- [x] Ollama adapter
- [x] OpenAI Responses API adapter
- [x] Anthropic Messages API adapter
- [x] PostgreSQL + pgvector memory
- [x] Memory retrieval injected into chat
- [x] Structured agent planner
- [x] Approval tokens
- [x] Sandboxed workspace tools
- [x] Next.js control surface
- [x] Tauri desktop shell scaffold
- [x] Windows setup/start scripts

## Phase 2 — coding workstation: DONE

- [x] Git status/diff tools
- [x] Multi-file change preview and approval
- [x] Restricted test/build runner
- [x] Repository selector restricted to configured roots
- [x] Explicit change approval UI
- [x] Tool-call activity timeline
- [x] Streaming chat for Ollama/OpenAI/Anthropic
- [x] Inspectable/searchable/deletable memory panel

## Phase 3 — integrations: IN PROGRESS

- [x] Approval-gated GitHub repository adapter
- [x] GitHub branch creation and pull-request tool
- [x] SHA-safe GitHub file update protection
- [x] MCP Python SDK v2 client
- [x] Allowlisted Streamable HTTP MCP registry
- [x] MCP tool discovery and approval-gated calls
- [ ] Optional web research broker
- [ ] Voice interface

## Phase 4 — team mode: CORE DONE

- [x] Shared task ledger
- [x] Architect / Builder / Reviewer roles
- [ ] Researcher role
- [x] Artifact-based handoffs
- [x] Stop conditions and agent-call budget controls
- [x] Human approval remains mandatory before applying generated changes
