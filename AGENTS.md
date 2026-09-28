# AGENTS.md — Genesis

## Goal
Build a local-first personal AI workspace that remains under explicit user control.

## Long-term vision

Genesis's end state is a local-first "app store"/launcher for AI and coding tools: a lightweight, minimal desktop catalog (Windows/Linux first, web later) where a user browses categories (code editors, terminals, local LLM/vision runtimes, other open-source AI tools) and one-click downloads, installs, and launches each entry — fully local, with a small progress indicator, no manual dependency wrangling. The existing Workbench/Runtime/Memory/Evolution surfaces remain one entry in that catalog, not the whole product. See `docs/APP_CATALOG_FEASIBILITY.md` for the feasibility research and `docs/ARCHITECTURE.md` for the planned design; see `PROJECT_STATUS.md` for phase status. This vision does not relax any rule below — it is the reason several of them exist.

## Non-negotiable architecture rules

- Prefer local Ollama models by default.
- Cloud providers must remain opt-in.
- Stateful/mutating tool calls require explicit approval.
- Tools must be scoped to the selected workspace/repository.
- Do not add self-deployment, self-copying, persistence outside user-selected paths, or unrestricted shell execution.
- Plans and diffs should be visible before changes are applied.
- Memory must be inspectable and deletable.

### Catalog/installer-specific rules (for the app-store direction)

- No arbitrary scripting as an install mechanism. Catalog entries are declarative manifests (identity, version, source URL, checksum, install/uninstall/launch commands, license tier, permissions), never an executable script with open-ended shell/file access — this is what separates Genesis from Pinokio's documented malware/CVE track record.
- Every install/launch action is approval-gated and scoped to `(app_id, version, manifest_hash)`, not just `app_id`, so a catalog update never silently inherits an old approval.
- Installs are transactional (stage → checksum-verify → commit, with deterministic rollback on failure), tracked in a local transaction log, not a flat file.
- Every catalog entry carries an explicit license tier (bundle directly / auto-fetch-and-install from vendor / fetch-and-handoff to user / avoid automating) and, for models, a separate weight license tag independent of runtime license. Proprietary IDE binaries (VS Code, Cursor, JetBrains) are never bundled or silently redistributed.
- Prefer wrapping native OS package managers (winget/brew/apt/flatpak) over a custom fetch-and-execute engine; a custom path is reserved for the uncataloged long tail and must still go through checksum verification and approval.
- New or updated catalog entries are subject to a freshness delay before becoming installable, and catalog validity (URLs, checksums) is checked by automation, not manual review alone.
- Sandboxing/install scope starts at workspace-local process isolation; anything beyond that (bubblewrap on Linux, Windows Sandbox on Windows) is opt-in per entry, never a promise Genesis can't keep.

## Stack

- Web: Next.js 16.3.x + React 19.2
- API: FastAPI
- Memory: PostgreSQL + pgvector
- Local model runtime: Ollama
- Desktop: Tauri 2

## Development priorities

1. Correctness and observability.
2. User approval boundaries.
3. Local operation.
4. Fast, minimal UI.
5. Replace agent chatter with concrete artifacts: plans, patches, test output, reviews.
