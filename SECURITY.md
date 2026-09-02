# Genesis security model

Genesis is a local-first AI workstation. The core security goal is simple: **models may propose, inspect, and reason broadly; side effects stay bounded, explicit, and attributable.**

## Authority boundaries

### Workspace

- Local file access resolves against the selected workspace root.
- Path traversal outside that root is rejected.
- Recursive Explorer scans omit dependency, VCS, build, and cache trees.
- Individual writes and multi-file change sets have configured byte limits.
- Generated code is not applied automatically.
- Phase 9 setup verifies a selected project with read-only directory access; setup write probes are confined to Genesis-owned application data.

### Tool broker

- `/v1/tools/read` accepts only registered non-mutating tools.
- Mutating tools use proposal -> short-lived approval ID -> explicit execution.
- Approval IDs are single-use and expire.
- Execution reuses the exact server-stored tool name/arguments; callers cannot swap arguments after approval.

### Commands

Genesis does not register an unrestricted shell.

The built-in project runner exposes only fixed check families: Python compile/test, npm build/test, and Cargo check/test. They launch without a shell and with a workspace-bounded cwd. Workbench xterm is output-only and has stdin disabled.

## Phase 9 installer / first-run / repair

The Windows installer owns first-run AI configuration. The same verifier is reused later for repair routing.

### Local Ollama setup

- Existing Ollama installations are detected before install actions.
- Preferred installation uses fixed `winget install` arguments for exact package `Ollama.Ollama`.
- If winget is unavailable/fails, Genesis downloads `OllamaSetup.exe` only from the fixed official Ollama URL.
- The fallback executable must have a valid Windows Authenticode signature before Genesis executes it.
- Silent installer arguments are fixed by Genesis and contain no model/user text.
- Model names are length/character validated and passed as one `ollama pull` argument.
- Ollama starts with fixed `serve` argv rather than a shell string.
- Final verification queries Ollama directly and requires both the selected chat model and `nomic-embed-text` before installer completion.

### Hardware inspection

Hardware-aware recommendations use one fixed internal Windows PowerShell query for OS memory, system-drive free space, and GPU display name.

- No user or model text is interpolated into that command.
- Hardware data is used only for conservative recommendation UI.
- GPU name is informational; Genesis does not infer unsafe or unreliable VRAM guarantees from it.
- Users may choose another curated model explicitly.

### Cloud setup

- OpenAI and Anthropic credentials are validated against the **exact selected model** through each provider's retrieve-model endpoint.
- Cloud model IDs are length/character validated before use in a fixed provider URL shape.
- API keys are stored through the operating-system credential store.
- `setup.json` contains only non-secret completion/provider/model/workspace state.
- The packaged sidecar receives a stored key only through its process environment.
- Setup UI never writes a cloud key into the workspace/repository or ordinary config files.

### Native setup verification

`Finish installation` is gated by a native verifier that checks:

- Genesis application-data writability using a temporary probe inside app data only;
- valid completed `setup.json` state;
- read access to the selected project or starter workspace;
- Ollama service/models for local mode, or secure credential presence for cloud mode.

A normal desktop start runs the same verifier. Failed verification routes to **First-run / Repair** rather than treating stale configuration as healthy.

### Installer behavior

- Interactive NSIS installs wait for Genesis Setup before completion.
- Silent installs remain non-interactive and defer setup until normal launch.
- Already-configured upgrades skip a forced interactive wizard, but normal startup verification still detects runtime drift.
- Workbench is not treated as ready until native setup verification and packaged sidecar health succeed.

## Desktop durable storage

The installed desktop uses a Genesis-owned SQLite database under Windows application data. This removes the need to install/run a privileged external database service for the normal desktop path.

- SQLite is opened only by the local packaged sidecar.
- Desktop embeddings are stored as JSON arrays; bounded cosine ranking occurs in-process.
- PostgreSQL + pgvector remains supported for source/server deployments.
- PostgreSQL retains database row locking for concurrent schedule claiming.
- The single-sidecar SQLite path uses an in-process claim lock to prevent local scheduler/manual-run races.

SQLite is an application durability boundary, not an encrypted secret vault. Cloud API keys remain in the OS credential store rather than the database.

## Workbench AI modes

- **Plan** invokes the planner only.
- **Build/Fix** use bounded coding-team flows and stop at proposals/review.
- **Review** sends the current read-only Git diff to the selected model and has no mutation authority.
- None of these modes bypass the existing tool approval broker.

## External workers

External workers are disabled unless explicitly configured server-side in `EXTERNAL_WORKERS_JSON`.

- Command workers use a fixed argv array and `asyncio.create_subprocess_exec`.
- Task text arrives on stdin and is not interpolated into a shell command.
- Worker cwd is restricted to the selected workspace.
- HTTP workers use explicitly configured HTTP(S) endpoints and bounded output/timeouts.
- Optional bearer tokens are loaded from named environment variables and are not returned to clients.
- External workers execute only through approval-gated `worker.run`.
- `/v1/workers/run` accepts the bounded built-in Genesis team only.

## GitHub and MCP

- GitHub credentials remain server-side.
- Existing-file replacement is SHA-safe; stale writes are rejected.
- MCP destinations come only from `MCP_SERVERS_JSON`.
- MCP side-effect-capable calls require approval.

## Research and voice

- Web research routes only through configured SearXNG.
- Result URLs are bounded to HTTP(S) and source IDs are preserved.
- Voice transcription invokes only the configured whisper.cpp executable/model with fixed argv.
- Audio input is size-limited WAV data.

## Durable runtime and evolution

- Team runs have a hard model-call budget.
- Team runs stop at proposals/review and do not auto-apply workspace changes.
- Schedules use the same bounded team and do not create a mutation bypass.
- Durable tasks preserve artifacts/events for inspection and replay.
- Evolution is shadow-first; deterministic gates and explicit human promotion are required.
- A promoted candidate does not autonomously rewrite source code/configuration.

## Secrets

Do not commit `.env` or provider tokens. Packaged desktop cloud keys use the OS credential store. Developer/source mode may still use environment variables or uncommitted `.env` files.

## Network exposure

The default API host is loopback-only (`127.0.0.1`). Deliberately exposing Genesis beyond localhost changes its threat model. Add authentication/reverse-proxy controls before treating it as multi-user software; the approval broker assumes the local UI user is the authority granting approvals.

## Desktop signing and updates

A release is not Authenticode-signed merely because CI produced an installer. Genuine signing requires a real signing identity/certificate in the release environment.

The Ollama fallback signature check validates the downloaded **Ollama** installer; it does not sign the **Genesis** installer.

Genesis does not enable automatic self-update installation until there is a cryptographically verified signed-update path. This is intentional; an unsigned updater would weaken the trust boundary.

## Reporting vulnerabilities

For private deployments, rotate any exposed credential and preserve relevant task/event logs. For repository vulnerabilities, use a private GitHub security advisory when available rather than publishing secrets or exploit details in a public issue.
