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
- **2026-09-28 — Tauri 2's capability/ACL system is the actual security boundary for install/launch, not an implementation detail.** Privileged install operations go in narrowly-scoped Rust/Tauri commands (one scope per action class), never a generic shell passthrough. FastAPI keeps catalog validation and approval-token issuance; approval tokens are scoped to `(app_id, version, manifest_hash)`.
- **2026-09-28 — Wrap native package managers (winget/brew/apt/flatpak) before writing a custom fetch-and-run engine.** Inherits their checksum/signature verification and, on Windows, avoids the SmartScreen cold-start reputation problem a fully custom downloader would face for every third-party binary.

## Where things live

- `AGENTS.md` — binding architecture rules (includes the catalog/installer-specific rules added 2026-09-28)
- `PROJECT_STATUS.md` — phase-by-phase status; Phase 9 tracks the app-catalog/launcher work (research complete, not started)
- `docs/ARCHITECTURE.md` — technical design, including the "Planned: local app catalog / launcher" section
- `docs/APP_CATALOG_FEASIBILITY.md` — full deep-research report (prior art, legal/licensing tiers, manifest/sandboxing architecture, packaging tooling, MVP scoping, risk register) with citations
- `SECURITY.md` — current threat boundaries for the shipped 0.9 workstation (does not yet cover the catalog/launcher, since it isn't built)

## Open questions / not yet decided

- Exact manifest schema field names/types (draft direction is in `docs/ARCHITECTURE.md`, not yet finalized as a schema file or Pydantic model)
- Whether the install-transaction SQLite store lives inside the Tauri app data dir or alongside the existing FastAPI-managed local state
- Full legal text confirmation for Cursor's ToS on automated installation (flagged as an open gap in the research — default to the conservative "fetch-and-handoff" tier until confirmed)
- macOS/Gatekeeper implications were out of scope for the initial research (Windows/Linux only); needed before any macOS catalog support
