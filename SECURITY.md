# Genesis security model

Genesis is a local-first AI workstation. The core security goal is simple: **models may propose, inspect, and reason broadly; side effects stay bounded, explicit, and attributable.**

## Authority boundaries

### Workspace

- Local file access resolves against the selected workspace root.
- Path traversal outside that root is rejected.
- Recursive Explorer scans omit dependency, VCS, build, and cache trees.
- Individual writes and multi-file change sets have configured byte limits.
- Generated code is not applied automatically.

### Tool broker

- Read-only tools may be called through `/v1/tools/read` only when the registered tool is marked non-mutating.
- Mutating tools use proposal -> short-lived approval ID -> explicit execution.
- Approval IDs are single-use and expire.
- Execution uses the tool name and exact arguments stored with the approval; callers cannot swap arguments after approval.

### Commands

Genesis does not register an unrestricted shell.

The built-in project runner exposes only fixed check families:

- Python compile
- Python tests
- npm build
- npm tests
- Cargo check
- Cargo tests

Commands launch without a shell and with a workspace-bounded working directory. The Workbench xterm component is output-only and has stdin disabled.

### Phase 9 installer / first-run setup

The Windows installer owns first-run AI configuration. This setup bridge is intentionally narrower than Genesis's normal tool system.

Local Ollama setup:

- Existing Ollama installations are detected before any install action.
- Preferred installation uses fixed `winget install` arguments for the exact `Ollama.Ollama` package.
- If winget is unavailable or fails, Genesis downloads `OllamaSetup.exe` only from the fixed official `https://ollama.com/download/OllamaSetup.exe` endpoint.
- The fallback executable must report a valid Windows Authenticode signature before Genesis executes it.
- Fallback silent installer arguments are fixed by Genesis and contain no model/user text.
- Model names are character/length validated before they are passed as a single `ollama pull` argument.
- Genesis starts Ollama using a fixed `serve` argument rather than interpolating a shell command.

Cloud setup:

- OpenAI and Anthropic keys are validated against the configured provider before setup is marked complete.
- API keys are stored through the operating-system credential store.
- `setup.json` contains only non-secret completion/provider/model state.
- The packaged sidecar receives a stored key only through its process environment.
- Setup UI never writes a cloud API key into the repository or normal application configuration.

Installer behavior:

- Interactive NSIS installs wait for Genesis Setup before completing.
- Silent installs do not launch an interactive wizard.
- Existing configured upgrades do not force the setup wizard again.
- An incomplete first launch remains setup-gated; the Workbench is not treated as ready until configuration and local sidecar health succeed.

### External workers

External workers are disabled unless explicitly configured server-side in `EXTERNAL_WORKERS_JSON`.

- Command workers use a fixed argv array and `asyncio.create_subprocess_exec`.
- The task arrives on stdin; model/user text is not interpolated into a shell command.
- Worker cwd is restricted to the selected workspace.
- HTTP workers require an explicitly configured HTTP(S) endpoint.
- Optional worker bearer tokens are loaded from named environment variables and are not returned to clients.
- External workers can execute only through the approval-gated `worker.run` tool.
- `/v1/workers/run` accepts the built-in bounded Genesis team only.

### GitHub and MCP

- GitHub credentials remain server-side.
- Existing GitHub file replacement is SHA-safe; stale writes are rejected.
- MCP destinations come only from `MCP_SERVERS_JSON`.
- MCP side-effect-capable calls require approval.

### Research and voice

- Web research routes only through configured SearXNG.
- Result URLs are bounded to HTTP(S) and source IDs are preserved.
- Voice transcription invokes only the configured whisper.cpp executable/model with a fixed argument shape.
- Audio input is size-limited WAV data.

### Durable runtime

- Team runs have a hard model-call budget.
- Team runs stop at proposals/review; they do not auto-apply workspace changes.
- Schedules run the same bounded team and therefore do not create a mutation bypass.
- Durable tasks store artifacts and ordered events for later inspection/replay.

### Evolution

Evolution V1 is shadow-first.

- Variant count and evaluation-case count are bounded.
- Baseline and candidate results are recorded.
- Deterministic gates must pass before promotion.
- Promotion requires explicit human approval.
- A promoted candidate does not autonomously rewrite source code or configuration.

## Secrets

Do not commit `.env` or provider tokens. Use restricted credentials wherever possible. Packaged desktop cloud keys use the OS credential store; developer/source mode may still use environment variables or `.env` files that must remain uncommitted.

## Network exposure

The default API host is loopback-only (`127.0.0.1`). Deliberately exposing Genesis beyond localhost changes its threat model. Add an authentication/reverse-proxy layer before treating it as multi-user software; the approval broker assumes the person using the local Genesis UI is the authority granting approvals.

## Desktop signing

A release is not considered Authenticode-signed merely because CI produced a Windows installer. Genuine signing requires a real certificate/signing identity supplied to the release environment.

The Phase 9 Ollama fallback signature verification protects the downloaded **Ollama** installer; it does not sign the **Genesis** installer itself.

## Reporting vulnerabilities

For private deployments, rotate any credential that may have been exposed and preserve the relevant task/event logs. For repository vulnerabilities, open a private GitHub security advisory when available instead of posting secrets or exploit details in a public issue.
