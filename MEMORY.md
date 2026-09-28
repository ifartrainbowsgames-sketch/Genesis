# MEMORY.md — Genesis project memory

This file is persistent cross-session context for anyone (human or AI agent) picking up Genesis work. It is **not** `AGENTS.md` (which holds binding architecture rules) and it is **not** Genesis's own in-app cognitive-memory feature (episodic + consolidated knowledge in PostgreSQL, described in `docs/ARCHITECTURE.md`). This is project-level institutional memory: the "why," the decisions made, and where to look for detail — kept as plain markdown so it survives outside any database and any single session.

Update this file when a decision is made that a future session would otherwise have to rediscover. Keep entries short; link to the fuller doc instead of duplicating it.

---

## Vision (as of 2026-09-28)

Genesis's original framing was "a local-first personal AI workstation" (chat, coding, research, voice, memory, durable agent runs). The actual end goal, clarified by the project owner, is bigger:

> A local-first "app store" for AI and dev tooling — one lightweight launcher where all the tools a coder needs (editors like VS Code/Cursor-alternatives, terminals, local open-source AI models for chat/vision/image-to-text/etc.) live in a categorized catalog. One click downloads, installs, and launches each tool, fully local, with a minimal progress bar — like a Microsoft Store / Play Store, but for local dev+AI tooling, aimed at solo "nerd coder" users. Windows and Linux first, web later.

The existing Workbench/Runtime/Memory/Evolution workstation is **one entry in that future catalog**, not the whole product. This does not replace any of AGENTS.md's non-negotiable rules (local-first default, approval-gated mutation, workspace scoping, no unrestricted shell, visible plans/diffs, inspectable/deletable memory) — it's an additional product surface that has to be built to honor those same rules, which is why the catalog/installer-specific rules were added to AGENTS.md rather than treated as a separate, looser system.

## Key decisions log

- **2026-09-28 — Scope the app-store MVP to one axis, not everything at once.** Every comparable surviving project (Ollama, Jan.ai, LM Studio, Stability Matrix) launched narrow and grew catalog breadth later via a pull mechanism; the one project that launched broad (Pinokio) did so by accepting arbitrary shell scripting as its install mechanism and has a real, documented malware/CVE track record as a result. Decision: MVP catalog = Ollama-compatible models (via Ollama's own registry) + 2-3 MIT/Apache terminal emulators. IDEs, vision models, and general catalog breadth come later. Full reasoning: `docs/APP_CATALOG_FEASIBILITY.md`.
- **2026-09-28 — Manifests are declarative, never scripts.** Catalog entries describe install/uninstall/launch as fixed fields (source URL, checksum, command), not an embedded scripting language. This is the specific thing that separates Genesis's planned design from Pinokio's risk profile.
- **2026-09-28 — Proprietary IDEs are hand-off or vendor-CLI only, never bundled.** VS Code's and Cursor's official binaries cannot be legally redistributed by Genesis; the plan is fetch-official-installer-and-handoff for both, and JetBrains IIs specifically via JetBrains' own Toolbox CLI silent-install path. Four-tier license framework (bundle / auto-fetch-install / fetch-handoff / avoid) lives in `docs/APP_CATALOG_FEASIBILITY.md` and is now a required manifest field per AGENTS.md.
- **2026-09-28 — Tauri 2's capability/ACL system was the original plan for the security boundary, but Phase 9A shipped without it.** Original intent: privileged install operations in narrowly-scoped Rust/Tauri commands. What was actually built: install/launch/uninstall run server-side in FastAPI (`app/services/catalog.py`) via fixed-argv `asyncio.create_subprocess_exec`/`subprocess.Popen`, `shell=False` — the same pattern as external command workers and project checks — registered as ordinary approval-gated tools. Reasoning at implementation time: one execution/approval model beats two; Genesis has no existing precedent anywhere else in the codebase for privileged logic living in Rust rather than FastAPI, and introducing that split just for this one feature would be inconsistent. Approval tokens are still scoped to `(app_id, version, manifest_hash)` via the existing generic approval-broker arguments dict. Moving to Tauri-enforced capabilities remains open future hardening (`PROJECT_STATUS.md` Phase 9A), not abandoned, just not required for the MVP to be safe (fixed argv + approval gate + freshness delay already close the gap that matters).
- **2026-09-28 — Wrap native package managers (winget/Ollama's own pull) before writing a custom fetch-and-run engine.** Implemented as planned: the only two `install_type`s are `winget` and `ollama_pull`; no custom downloader exists. Inherits their checksum/signature verification and, on Windows, avoids the SmartScreen cold-start reputation problem a fully custom downloader would face for every third-party binary.
- **2026-09-28 — Install-state tracking uses the existing PostgreSQL database, not a separate SQLite store.** `CatalogInstallation`/`CatalogTransaction` tables were added to `app/models.py` alongside every other Genesis table, for the same one-datastore-not-two reasoning as the Tauri deviation above. It gets the same graceful degradation (works without persistence) as everything else when PostgreSQL isn't running.
- **2026-09-28 — Phase 9A pipeline shipped and tested.** Manifest schema (`CatalogManifest`), seed catalog (2 winget terminals + 2 Ollama models, `apps/server/catalog/index.json`), install/launch/uninstall/list tools, manifest-hash-scoped approval, 72h freshness delay, and the `/apps` Next.js page are all implemented and covered by `apps/server/tests/test_catalog.py` (25 tests, all passing) plus a full server test suite run (67 passing) and a clean `next build`. Phase 9B (CI catalog validation, security audit pass, structured per-model weight license tag) and 9C (Linux package managers, IDE hand-off, vision models, sandboxing, community manifests) are not started.
- **User mentioned `pkgs.win` (a relative's site, a winget-package-adjacent index) mid-build as a possible future catalog source.** Not investigated (network egress to that domain is blocked in this sandbox, and the user dropped the thread with "never mind"). Worth revisiting for Phase 9C's community-manifest idea if raised again.

## Where things live

- `AGENTS.md` — binding architecture rules (includes the catalog/installer-specific rules added 2026-09-28)
- `PROJECT_STATUS.md` — phase-by-phase status; Phase 9A is implemented, 9B/9C are planned
- `docs/ARCHITECTURE.md` — technical design under "Local app catalog / launcher (Phase 9)", reflects what's actually built
- `docs/APP_CATALOG_FEASIBILITY.md` — full deep-research report (prior art, legal/licensing tiers, manifest/sandboxing architecture, packaging tooling, MVP scoping, risk register) with citations
- `apps/server/app/services/catalog.py` — install/launch/uninstall/list logic
- `apps/server/app/schemas.py` — `CatalogManifest`/`CatalogEntry`/`CatalogActionResult`
- `apps/server/app/models.py` — `CatalogInstallation`/`CatalogTransaction` tables
- `apps/server/catalog/index.json` — the seed catalog data
- `apps/server/tests/test_catalog.py` — coverage for hash-scoping, freshness gate, fixed-argv install/uninstall, rollback
- `apps/web/app/apps/page.tsx` — the catalog UI, linked from the nav as "Apps"
- `SECURITY.md` — current threat boundaries for the shipped 0.9 workstation (does not yet cover the catalog/launcher — worth a pass before Phase 9B ships)

## Open questions / not yet decided

- Whether/when to move install/launch execution into scoped Tauri commands for the second, structural enforcement layer the original research recommended (see decision log above) — not required for current safety, but the stronger long-term design
- Structured per-model weight license tagging (currently just free-text in `license_note`) before the model catalog grows past the two seed entries
- Full legal text confirmation for Cursor's ToS on automated installation (flagged as an open gap in the research — default to the conservative "fetch-and-handoff" tier until confirmed)
- macOS/Gatekeeper implications were out of scope for the initial research (Windows/Linux only); needed before any macOS catalog support
- Linux install path for the seed catalog (Alacritty declares `linux` as a supported platform in the manifest but there's no apt/flatpak installer wired up yet — Windows via winget only for now)
