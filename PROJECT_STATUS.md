# Genesis project status

Genesis 0.9 is the convergence release: the original workstation foundation plus the Workbench, durable runtime, cognitive memory, external-worker boundary, shadow evolution, stronger CI, Doctor diagnostics, and versioned desktop artifact workflow.

## Phase 1 — foundation: DONE

- [x] Monorepo layout
- [x] FastAPI API
- [x] Ollama adapter
- [x] OpenAI Responses API adapter
- [x] Anthropic Messages API adapter
- [x] PostgreSQL + pgvector memory
- [x] Structured agent planner
- [x] Approval tokens
- [x] Sandboxed workspace tools
- [x] Next.js control surface
- [x] Tauri desktop shell
- [x] Windows setup/start/Doctor scripts

## Phase 2 — coding workstation: DONE

- [x] Git status/diff tools
- [x] Multi-file change preview and approval
- [x] Restricted fixed-command test/build runner
- [x] Repository selector restricted to configured roots
- [x] Streaming chat
- [x] Workbench route with filtered Explorer
- [x] Monaco editor
- [x] Output-only xterm check console (`stdin` disabled)
- [x] Git diff/status panel
- [x] Task/worker side panel
- [x] Workbench saves and checks use proposal -> single-use approval -> execution
- [x] Read-only tool endpoint refuses mutating tools

## Phase 3 — integrations and workers: DONE FOR V1

- [x] Approval-gated GitHub repository adapter
- [x] SHA-safe GitHub file update protection
- [x] MCP Python SDK v2 client
- [x] Allowlisted Streamable HTTP MCP registry
- [x] Source-tracked SearXNG research broker
- [x] Local whisper.cpp speech-to-text path
- [x] Unified worker registry
- [x] Built-in bounded Genesis team worker
- [x] Fixed-argv command worker adapter with `shell=False`
- [x] Allowlisted HTTP worker adapter
- [x] External workers execute only through approval-gated `worker.run`
- [x] Direct external-worker endpoint bypass closed by regression test

External products such as Claude Code, Codex, OpenHands, or Wayland can be connected through an explicitly configured command or HTTP adapter. Genesis does not auto-discover or launch arbitrary executables.

## Phase 4 — durable multi-agent runtime: DONE FOR V1

- [x] Architect / optional Researcher / Builder / Reviewer artifact handoffs
- [x] Hard 1–4 model-call budget
- [x] Persistent task ledger
- [x] Immutable `team_request` replay artifact
- [x] Ordered persistent run-event log
- [x] Task detail API with artifacts + events
- [x] Retry with lineage (`retry_of` artifact)
- [x] Durable interval schedules in PostgreSQL
- [x] Schedule locking with `FOR UPDATE SKIP LOCKED`
- [x] Schedule pickup advances `next_run_at` before execution to avoid duplicate slow-run pickup
- [x] Runtime UI for tasks, event history, retries, workers, and schedules
- [x] Scheduled team runs still stop before workspace mutation

## Phase 5 — cognitive memory: DONE FOR V1

- [x] Episodic conversation records retained unchanged
- [x] Separate cognitive-memory table
- [x] Semantic conversation summaries
- [x] Procedural/user-constraint extraction
- [x] Source record IDs retained on consolidated memory
- [x] Confidence + embeddings on cognitive items
- [x] Cognitive memory search is injected beside episodic retrieval in chat
- [x] Memory UI shows episodic and cognitive layers separately
- [x] User-triggered consolidation and search

The first consolidation algorithm is deliberately deterministic and inspectable. It does not delete or rewrite the source episodes.

## Phase 6 — evolution V1: DONE

- [x] Bounded prompt variant generation (maximum 3 per run)
- [x] Bounded evaluation cases (maximum 10 per run)
- [x] Baseline and candidate execution through the selected model provider
- [x] Deterministic expected/forbidden substring gate before any promotion
- [x] Per-case results and latency captured
- [x] Candidate/eval history stored in PostgreSQL
- [x] Shadow status by default
- [x] Manual promotion only
- [x] Promotion requires every deterministic case to pass and candidate score to meet/beat baseline
- [x] Prior promoted candidate can be re-promoted later, providing a manual rollback path
- [x] Evolution UI exposes scores, baseline, failures, and promotion gate

Evolution V1 intentionally does **not** autonomously rewrite live code, prompts, or configuration. Promotion records a reviewed winning prompt version; applying evolved behavior to additional runtime surfaces remains an explicit product decision.

## Phase 7 — test and release hardening: DONE EXCEPT SIGNING / FULL EXTERNAL-SERVICE E2E

- [x] 42-test Phase 5A safety baseline established before the 0.9 work
- [x] Regression coverage for approval, workspace, planner, memory fallback, GitHub SHA safety, MCP, research, and restricted checks
- [x] New worker/evolution/cognitive-memory authority tests
- [x] PostgreSQL + pgvector service added to server CI
- [x] Database integration coverage for task events, artifacts, cognitive consolidation, and schedules
- [x] Web production build gate
- [x] Windows PyInstaller FastAPI sidecar packaging gate
- [x] Windows Tauri/Rust compile gate
- [x] Current GitHub Actions majors and deduplicated PR CI
- [x] Versioned tag-triggered Windows bundle artifact workflow
- [x] Doctor script + in-app dependency diagnostics
- [ ] Windows Authenticode/installer signing — requires a real signing certificate/identity secret
- [ ] Full packaged-desktop E2E with real Ollama + SearXNG + optional whisper.cpp on the Windows runner

## Safety invariants

- No unrestricted shell tool.
- Local paths cannot escape the selected workspace.
- Recursive Explorer scans skip `.git`, dependency, build, and cache trees.
- Mutating registered tools require short-lived single-use approval tokens.
- External workers are server-side allowlisted and approval-gated.
- Command workers use fixed argv and `create_subprocess_exec`, not a shell.
- Team runs and schedules are bounded and stop before applying workspace changes.
- Evolution candidates never auto-promote.
- Cloud providers are optional.

## Remaining release blockers that cannot be fabricated in source control

1. Supply a real Windows signing identity/certificate and wire its secrets into the release environment.
2. Decide which external workers should be officially supported/configured by default; the runtime adapter is intentionally generic and allowlist-only.
3. Add expensive full external-service E2E runners when stable test credentials/models are available.
