# AGENTS.md — Genesis

## Goal
Build a local-first personal AI workspace that remains under explicit user control.

## Non-negotiable architecture rules

- Prefer local Ollama models by default.
- Cloud providers must remain opt-in.
- Stateful/mutating tool calls require explicit approval.
- Tools must be scoped to the selected workspace/repository.
- Do not add self-deployment, self-copying, persistence outside user-selected paths, or unrestricted shell execution.
- Plans and diffs should be visible before changes are applied.
- Memory must be inspectable and deletable.

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
