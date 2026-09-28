# Genesis project status

Genesis 0.9 preserves the roadmap explicitly as **5A → 5B → 5C → 6 → 7 → 8**. Earlier foundation/integration/team work remains complete; this file focuses on the convergence roadmap.

The long-term direction beyond 0.9 is **Phase 9 — local app catalog/launcher** (see below): turning Genesis into a one-click local install/launch catalog for AI and dev tooling, with the current Workbench/Runtime/Memory/Evolution workstation becoming one catalog entry among others rather than the whole product. Phase 9 is in the research/planning stage; nothing in it is implemented yet.

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

Phase 5A was merged to `main` before the 0.9 convergence branch.

## Phase 5B — Workbench: DONE FOR 0.9

- [x] Filtered workspace Explorer
- [x] Monaco code editor
- [x] Approval-gated saves
- [x] Git status/diff panel
- [x] Restricted project-check selector
- [x] xterm check-output surface
- [x] xterm stdin disabled; not a general shell
- [x] Runtime task/worker side panel
- [x] Non-Git workspaces degrade gracefully
- [x] Read-only tool endpoint rejects mutating tools

## Phase 5C — durable runtime and external workers: DONE FOR 0.9

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
- [x] Fixed-argv command worker adapter using `create_subprocess_exec`
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

The V1 consolidator is deterministic and inspectable. It does not delete or rewrite source episodes.

## Phase 7 — evaluation and evolution V1: DONE

- [x] Bounded prompt variant generation (maximum 3)
- [x] Bounded evaluation cases (maximum 10)
- [x] Baseline and candidate execution through the selected provider
- [x] Deterministic expected/forbidden-string gates
- [x] Per-case results + latency capture
- [x] Candidate/evaluation history in PostgreSQL
- [x] Shadow status by default
- [x] Manual promotion only
- [x] Promotion requires all deterministic cases to pass and score to meet/beat baseline
- [x] Prior passing candidates can be promoted again for manual rollback
- [x] Evolution UI exposes baseline, scores, failures, and promotion controls

Evolution V1 intentionally does not autonomously rewrite live code, prompts, or configuration.

## Phase 8 — production/release hardening: COMPLETE FOR UNSIGNED 0.9 RELEASE CANDIDATE

### Test gates

- [x] Server compile + pytest
- [x] Real PostgreSQL + pgvector service in CI
- [x] Database integration coverage for task events/artifacts/cognitive memory/schedules
- [x] Web production/static-export build gate
- [x] Windows PyInstaller sidecar packaging gate
- [x] Packaged Windows sidecar launch + `/health` runtime smoke gate
- [x] Tauri/Rust compile gate
- [x] Current GitHub Actions majors
- [x] PR CI deduplicated with concurrency cancellation

### Startup / Doctor

- [x] `scripts/doctor.ps1` prerequisite + live-health diagnostics
- [x] Expanded in-app Diagnostics for workers/scheduler/cognitive memory/evolution
- [x] `scripts/start.ps1` can start PostgreSQL/pgvector + SearXNG, check Ollama, launch API/web, and verify API readiness
- [x] Clear degraded behavior when optional/local dependencies are unavailable

### Release

- [x] Workspace/web/desktop/runtime versions aligned to 0.9.0
- [x] Tag-triggered Windows bundle workflow
- [x] Workflow artifact upload
- [x] GitHub Release creation and bundle upload on `v*` tags
- [x] README updated for 0.9
- [x] Security boundaries documented in `SECURITY.md`
- [x] Architecture/status truth pass
- [ ] Authenticode/installer signing — requires a real signing certificate/identity supplied as release secrets

### External-service E2E still optional, not a merge blocker

- [ ] Full Windows runner E2E using a real Ollama model download
- [ ] Full SearXNG live-query E2E
- [ ] whisper.cpp live transcription E2E

Those tests are intentionally not fabricated: they require expensive external downloads/services. The packaged sidecar itself is launched and health-checked in CI.

## Safety invariants

- No unrestricted shell tool.
- Local paths cannot escape the selected workspace.
- Recursive Explorer scans skip VCS, dependency, build, virtualenv, target, and cache trees.
- Mutating tools require short-lived single-use approval tokens.
- Exact approved tool arguments are stored server-side and reused at execution.
- External workers are server-side allowlisted and approval-gated.
- Command workers use fixed argv and no shell.
- Team runs and schedules are bounded and stop before applying workspace mutations.
- Evolution candidates never auto-promote.
- Cloud providers remain optional.

## Phase 9 — local app catalog/launcher: 9A PIPELINE PROVEN

Feasibility research is done (`docs/APP_CATALOG_FEASIBILITY.md`); design direction is summarized in `docs/ARCHITECTURE.md`. Phase 9A's install/approval pipeline is implemented and tested end-to-end (server-side); the Next.js `/apps` catalog page is live. Phase 9B/9C are not started.

**Implementation note — deviation from the original design sketch:** install/launch/uninstall execute server-side in FastAPI (`app/services/catalog.py`), using the same fixed-argv `asyncio.create_subprocess_exec` (`shell=False`) pattern already used for external command workers and project checks, registered as ordinary approval-gated tools (`catalog.install`/`catalog.launch`/`catalog.uninstall`/`catalog.list`) — not as new Tauri/Rust commands. This keeps one execution/approval model across the whole app instead of introducing a second one, at the cost of not yet getting Tauri's ACL as a second, structural enforcement layer. Moving privileged execution into scoped Tauri commands remains a valid future hardening step (tracked below), not a blocker for the MVP. Similarly, install-state/transaction tracking uses the existing PostgreSQL database (`CatalogInstallation`, `CatalogTransaction` tables in `app/models.py`) rather than a separate local SQLite store, for the same one-datastore-not-two reason; it still gets the same graceful-degradation behavior as every other Genesis table (works, just without persistence, when PostgreSQL is unavailable).

### Phase 9A — pipeline proof

- [x] Manifest schema (identity/version/source/install/uninstall/launch/license tier/platform) — `CatalogManifest` in `app/schemas.py`; no checksum field yet since winget/Ollama each verify their own downloads (see 9B)
- [x] Install-state/transaction tracking with stage → commit/rollback (PostgreSQL tables, not SQLite — see deviation note above)
- [x] Approval token scoped to `(app_id, version, manifest_hash)` — generic approval-broker arguments carry `manifest_hash`; `install_app`/`launch_app` reject a stale hash
- [ ] Tauri 2 capability/scope design: narrow Rust commands per install-action class (deferred — see deviation note above)
- [x] MVP catalog: 2 terminals (Windows Terminal, Alacritty via winget) + 2 Ollama models (`apps/server/catalog/index.json`)
- [x] `/apps` catalog UI (Next.js) — browse, install, launch, uninstall with approval confirmation

### Phase 9B — hardening before catalog growth (planned)

- [x] Freshness delay on new/updated catalog entries before they become installable (`catalog_freshness_hours`, default 72h)
- [ ] Scheduled CI job validating catalog URLs/checksums, bot-filed PRs on drift (never auto-merged)
- [ ] Security audit of manifest-parsing path specifically (lower risk than the original archive-extraction concern since entries are plain JSON validated by Pydantic, not executable scripts — still worth a dedicated pass before catalog growth)
- [x] Per-entry `license_tier` field enforced in the manifest schema; per-model weight license detail currently lives in free-text `license_note` rather than a separate structured tag — worth splitting out before adding more model entries

### Phase 9C — catalog widening (not started, sequenced after 9B closes out)

- [x] Native package manager wrapping (winget) for the seed Windows entries — no custom fetch-and-run engine was built
- [ ] apt/brew/flatpak wrapping for Linux parity (seed catalog currently only installs terminals on Windows; Alacritty's Linux platform tag is declared but not yet wired to an installer)
- [ ] Vendor hand-off flow for proprietary IDEs (VS Code, Cursor via fetch-and-handoff; JetBrains via their own Toolbox CLI) — never bundled/redistributed
- [ ] Vision/image-to-text model category
- [ ] Optional sandboxing tier (bubblewrap on Linux, Windows Sandbox config on Windows) per catalog entry
- [ ] Community-submitted manifests (e.g. a winget-pkgs-style third-party feed) gated by the same approval + automated audit CI as built-in entries

## Final release condition

Genesis 0.9 is ready to merge when PR #2 is green on **server + PostgreSQL/pgvector, web build, packaged Windows sidecar runtime, and Tauri compile**. After merge, a `v0.9.0` tag can build and publish the Windows release artifacts. Genuine Windows signing remains dependent on a real certificate.
