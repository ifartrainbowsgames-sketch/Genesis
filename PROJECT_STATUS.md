# Genesis project status

Genesis 0.10 extends the completed **5A → 5B → 5C → 6 → 7 → 8** convergence roadmap with **Phase 9 — One-Click Genesis**.

## Phase 5A — reliability foundation: DONE / MERGED

- [x] Real pytest suite instead of import-only confidence
- [x] Approval single-use/expiry tests
- [x] Workspace traversal/write boundary tests
- [x] Planner parsing tests
- [x] Ollama embedding fallback regression coverage and production fix
- [x] Restricted project-command tests
- [x] GitHub SHA-safe replacement tests
- [x] MCP/research validation tests
- [x] Modernized/deduplicated GitHub Actions
- [x] Windows desktop icon/package defect fixed

## Phase 5B — Workbench: DONE

- [x] Filtered workspace Explorer
- [x] Monaco code editor
- [x] Approval-gated saves
- [x] Git status/diff panel
- [x] Restricted project-check selector
- [x] Output-only xterm check surface
- [x] Runtime task/worker panel
- [x] Non-Git workspaces degrade gracefully
- [x] Read-only tool endpoint rejects mutating tools
- [x] Bounded “Ask Genesis” team control directly in Workbench

## Phase 5C — durable runtime and external workers: DONE

- [x] Persistent task ledger
- [x] Immutable `team_request` replay artifact
- [x] Ordered persistent run-event log
- [x] Task detail API with artifacts/events
- [x] Retry with `retry_of` lineage
- [x] Durable PostgreSQL interval schedules
- [x] `FOR UPDATE SKIP LOCKED` schedule claiming
- [x] Advance `next_run_at` before execution to avoid duplicate slow-run pickup
- [x] Runtime UI for tasks/events/retries/schedules/workers
- [x] Unified worker registry
- [x] Built-in bounded Genesis team worker
- [x] Fixed-argv command worker adapter
- [x] Allowlisted HTTP worker adapter
- [x] External workers execute only through approval-gated `worker.run`
- [x] Direct external-worker execution bypass closed by regression coverage
- [x] Scheduled team runs still stop before workspace mutation

## Phase 6 — cognitive/project memory V1: DONE

- [x] Raw episodic conversation records preserved
- [x] Separate cognitive-memory table
- [x] Semantic conversation summaries
- [x] Procedural/user-constraint extraction
- [x] Source-record lineage retained
- [x] Confidence + optional pgvector embedding
- [x] Cognitive + episodic retrieval injected into chat
- [x] Separate Memory UI layers
- [x] User-triggered consolidation/search

## Phase 7 — evaluation and evolution V1: DONE

- [x] Bounded prompt variant generation
- [x] Bounded evaluation cases
- [x] Baseline/candidate execution through selected provider
- [x] Deterministic expected/forbidden-string gates
- [x] Per-case results + latency capture
- [x] Candidate/evaluation history in PostgreSQL
- [x] Shadow status by default
- [x] Manual promotion only
- [x] Promotion requires all deterministic cases to pass and meet/beat baseline
- [x] Manual rollback by re-promoting a prior passing candidate

## Phase 8 — production/release hardening: DONE FOR UNSIGNED RELEASES

- [x] Server compile + pytest
- [x] Real PostgreSQL + pgvector CI service
- [x] Database integration coverage
- [x] Web production/static-export build gate
- [x] Windows PyInstaller sidecar packaging gate
- [x] Packaged sidecar launch + `/health` and Tauri-origin CORS smoke gate
- [x] Tauri/Rust compile gate
- [x] Doctor/startup diagnostics
- [x] Tag-triggered GitHub Release workflow
- [x] Security/architecture/status documentation
- [ ] Authenticode signing — requires a real signing identity/certificate supplied as release secrets

## Phase 9 — One-Click Genesis installer: IMPLEMENTED / CI GATED

### Installer-owned setup

- [x] Windows bundle target narrowed to a real NSIS setup executable
- [x] NSIS post-install hook launches `Genesis.exe --installer-setup`
- [x] Installer waits for the Genesis setup window before completing
- [x] Successful interactive setup immediately launches the configured desktop app
- [x] Silent `/S` install remains non-interactive and defers setup to first launch
- [x] Existing configured installations skip the setup wizard during upgrades
- [x] Desktop launch is gated until setup is complete
- [x] Desktop startup waits for local sidecar health
- [x] First successful desktop startup lands directly in `/workbench`

### Local AI path

- [x] Detect existing Ollama installation
- [x] Detect whether Ollama API is already running
- [x] Preferred automatic install through fixed `winget` arguments
- [x] Fallback to official `OllamaSetup.exe` when winget is unavailable/fails
- [x] Fallback installer Authenticode signature must validate before execution
- [x] Silent Ollama installer arguments are fixed by Genesis
- [x] Start `ollama serve` automatically when needed
- [x] Curated local model selector
- [x] Pull selected chat model
- [x] Pull `nomic-embed-text` for local memory embeddings
- [x] Setup does not become complete until the model preparation succeeds

### Cloud AI path

- [x] OpenAI option
- [x] Anthropic option
- [x] API key is validated before setup completes
- [x] Secret stored through the operating-system credential store
- [x] `setup.json` stores provider/model choice only, never the API key
- [x] Desktop sidecar receives the stored key only as a process environment variable

### Workbench readiness

- [x] Installer-selected provider/model becomes the server default
- [x] Workbench “Ask Genesis” uses the installer-selected provider automatically
- [x] AI-generated changes remain proposals; Phase 9 creates no mutation bypass
- [x] Startup failure offers Diagnostics/retry rather than exposing a half-ready Workbench

### Phase 9 CI gate

- [x] Existing server + pgvector suite retained
- [x] Existing web production build retained
- [x] Existing packaged sidecar runtime test retained
- [x] Rust/Tauri setup bridge compile gate
- [x] CI builds the actual NSIS installer
- [x] CI executes the silent NSIS install path to ensure packaging/install does not hang or fail

Phase 9 is merge-ready only when the exact PR head is green on all three jobs, including the real NSIS bundle/install step.

## Safety invariants

- No unrestricted shell tool.
- Local paths cannot escape the selected workspace.
- Mutating tools require short-lived single-use approval tokens.
- Exact approved tool arguments are stored server-side and reused at execution.
- External workers remain server-side allowlisted and approval-gated.
- Command workers use fixed argv and no shell.
- Installer setup uses fixed provider-install commands; API keys never enter repository configuration.
- Downloaded Ollama fallback installer must pass Windows Authenticode verification before execution.
- Team runs and schedules remain bounded and stop before workspace mutation.
- Evolution candidates never auto-promote.

## Remaining non-code release requirement

A public production installer can be built and tested without a certificate, but a genuinely trusted Windows release still needs a real Authenticode signing certificate/identity configured in release secrets.
