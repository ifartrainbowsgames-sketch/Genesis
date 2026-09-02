# Genesis project status

Genesis 0.10 extends the completed **5A → 5B → 5C → 6 → 7 → 8** convergence roadmap with **Phase 9 — One-Click Genesis**.

## Phase 5A — reliability foundation: DONE / MERGED

- [x] Real pytest suite and authority-boundary regressions
- [x] Ollama embedding fallback production fix + coverage
- [x] Modern GitHub Actions and Windows package checks

## Phase 5B — Workbench: DONE

- [x] Filtered Explorer + Monaco editor
- [x] Approval-gated saves and fixed project checks
- [x] Git status/diff + output-only xterm
- [x] Task/worker history
- [x] Project snapshot on first open
- [x] Real Plan / Build / Fix / Review AI modes
  - Plan uses the planner only
  - Build uses the bounded coding team
  - Fix constrains the bounded team to minimal repair
  - Review is read-only against the current Git diff

## Phase 5C — durable runtime and workers: DONE

- [x] Persistent task ledger, artifacts, events, retries
- [x] Durable schedules
- [x] PostgreSQL multi-process claiming with `SKIP LOCKED`
- [x] SQLite single-sidecar claim lock
- [x] Built-in team + allowlisted external workers
- [x] External execution remains approval-gated

## Phase 6 — cognitive/project memory V1: DONE

- [x] Episodic + separate cognitive memory
- [x] Semantic summaries + procedural constraints
- [x] Source lineage and confidence
- [x] PostgreSQL pgvector ranking
- [x] Embedded SQLite vector storage + bounded in-process cosine ranking
- [x] Text fallback when embeddings are unavailable

## Phase 7 — evaluation/evolution V1: DONE

- [x] Bounded variants/cases
- [x] Baseline/candidate execution
- [x] Deterministic gates + history
- [x] Shadow-first candidates
- [x] Explicit manual promotion/rollback only

## Phase 8 — production/release hardening: DONE FOR UNSIGNED RELEASES

- [x] Server + real PostgreSQL/pgvector CI
- [x] Web production build
- [x] Windows packaged sidecar runtime/CORS test
- [x] Tauri/Rust compile gate
- [x] Doctor/startup diagnostics
- [x] Tag-triggered release workflow
- [x] Security/architecture/status documentation
- [ ] Authenticode signing — requires a real certificate/identity in release secrets

## Phase 9 — One-Click Genesis: IMPLEMENTED / FINAL CI REQUIRED

### Installer-owned setup

- [x] Real Windows NSIS setup target
- [x] NSIS launches `Genesis.exe --installer-setup` and waits
- [x] Silent `/S` install stays non-interactive
- [x] Existing configured upgrades skip forced interactive setup
- [x] Desktop startup verifies setup before Workbench
- [x] Healthy startup waits for sidecar then lands directly in `/workbench`
- [x] Unhealthy startup routes into First-run / Repair

### No hidden desktop database prerequisite

- [x] Installed desktop uses private app-data `genesis.db`
- [x] `aiosqlite` packaged with FastAPI sidecar
- [x] SQLAlchemy models support PostgreSQL + SQLite
- [x] PostgreSQL retains native pgvector
- [x] SQLite stores embedding arrays as JSON and cosine-ranks a bounded local candidate set
- [x] Tasks/events/schedules/memory/evolution persist without Docker/PostgreSQL
- [x] CI has a separate embedded SQLite schema/vector-storage smoke test
- [x] Packaged Windows sidecar CI uses the embedded database path

### Hardware-aware local AI

- [x] Detect total RAM
- [x] Detect free system-drive space
- [x] Report GPU name without pretending it guarantees model speed
- [x] Conservative automatic model recommendation
- [x] Curated stable-model list: `qwen3:4b`, `qwen3:8b`, `gpt-oss:20b`, `qwen3-coder:30b`
- [x] Detect/install/start Ollama
- [x] Fixed `winget` installation path
- [x] Verified official signed Ollama installer fallback
- [x] Pull selected chat model + `nomic-embed-text`

### Cloud AI

- [x] OpenAI + Anthropic choices
- [x] Current explicit model choices
- [x] Validate credential **and exact selected model access** before saving
- [x] Store secret in Windows credential store
- [x] Persist only non-secret provider/model configuration

### Native setup verification / repair

- [x] Genesis app-data write probe
- [x] Setup configuration check
- [x] Read-only selected-workspace check
- [x] Ollama service + selected model + embedding-model verification
- [x] Secure cloud credential presence check
- [x] `Finish installation` gated on all required checks being green
- [x] Same verifier reused on normal desktop startup
- [x] Repair flow does not write probe files into the selected project

### Workbench readiness

- [x] Installer-selected provider/model becomes sidecar default
- [x] Ask Genesis uses installer-selected AI automatically
- [x] Project snapshot appears immediately
- [x] Plan / Build / Fix / Review map to concrete bounded/read-only workflows
- [x] Generated changes remain proposals; no mutation bypass

### Final Phase 9 CI gate

The exact merge head must pass all of these before PR #3 is merged:

- [ ] Server pytest against real PostgreSQL + pgvector
- [ ] Embedded SQLite server smoke
- [ ] Web production build
- [ ] Packaged Windows sidecar with embedded SQLite
- [ ] Selected-provider system-health check
- [ ] Tauri-origin CORS check
- [ ] Rust/Tauri native setup compile
- [ ] Actual NSIS installer build
- [ ] Silent NSIS installation smoke test

These boxes are intentionally not pre-checked: they describe the **final exact-head validation**, not merely implemented workflow steps.

## Deliberately deferred / external release requirement

- [ ] Authenticode signing certificate/identity
- [ ] Signed automatic-update verification path

Genesis will not ship an unsigned self-updater merely to claim automatic updates. Release checking/manual installation is safer until updates can be cryptographically verified.

## Safety invariants

- No unrestricted shell tool.
- Local API binds to loopback by default.
- Workspace paths remain bounded.
- Mutating tools require short-lived single-use approval tokens.
- External workers remain allowlisted + approval-gated.
- Fixed project checks and fixed installer commands do not interpolate model/user text into a shell.
- Installer cloud credentials stay out of repository configuration.
- Downloaded Ollama fallback must pass Authenticode verification before execution.
- Team runs/schedules remain bounded and stop before workspace mutation.
- Evolution never auto-promotes.

## Merge condition

PR #3 is merge-ready only after the **exact final head** passes all three GitHub Actions jobs, including the actual NSIS bundle and silent installation step. After merge, `v0.10.0` can build/publish the Windows release. A publicly trusted signed installer still requires a real signing identity.
