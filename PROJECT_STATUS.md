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

## Phase 3 — integrations: CORE DONE

- [x] Approval-gated GitHub repository adapter
- [x] GitHub branch creation and pull-request tool
- [x] SHA-safe GitHub file update protection
- [x] MCP Python SDK v2 client
- [x] Allowlisted Streamable HTTP MCP registry
- [x] MCP tool discovery and approval-gated calls
- [x] Source-tracked SearXNG research broker
- [x] Bundled local SearXNG Docker service
- [x] Research workspace with inspectable source ledger
- [x] Local-first push-to-talk voice interface
- [x] Configured whisper.cpp speech-to-text backend
- [x] Optional operating-system speech synthesis for replies

## Phase 4 — team mode: CORE DONE

- [x] Shared task ledger
- [x] Architect / Builder / Reviewer roles
- [x] Researcher role
- [x] Optional Researcher → Builder source-tracked handoff
- [x] Artifact-based handoffs
- [x] Stop conditions and 1–4 agent-call budget controls
- [x] Human approval remains mandatory before applying generated changes

## Phase 5 — desktop packaging: IN PROGRESS

- [x] FastAPI PyInstaller sidecar entrypoint
- [x] Target-triple-aware Windows sidecar build script
- [x] Tauri externalBin configuration
- [x] Tauri shell-plugin sidecar launch
- [x] Windows CI job for sidecar packaging and Rust compile-check
- [ ] Verify packaged desktop runtime against local PostgreSQL/Ollama/SearXNG
- [ ] Installer signing
- [ ] First-run dependency health/setup screen
- [ ] Release artifacts and versioned installer workflow

## Next milestone

Finish release hardening: make the desktop build reproducible in CI, verify the packaged sidecar runtime, add dependency health diagnostics, and produce a signed versioned Windows installer workflow.
