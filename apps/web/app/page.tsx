"use client";

import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { useRouter } from "next/navigation";
import { api, genesisFetch, streamApi } from "../lib/api";
import styles from "./workbench-shell.module.css";

type Mode = "ask" | "plan" | "build" | "review";
type Turn = { role: "user" | "assistant"; content: string; meta?: string; context?: string[] };
type Workspace = { name: string; path: string; is_git: boolean; selected: boolean };
type WorkspaceList = { current: Workspace; candidates: Workspace[] };
type AgentPlan = {
  goal: string;
  steps: Array<{ id: number; title: string; description: string; tool?: string | null }>;
  notes: string[];
};
type FileChange = { path: string; action: "create" | "replace"; content: string; reason?: string };
type RecommendedCheck = {
  kind: "python_compile" | "python_test" | "npm_build" | "npm_test" | "cargo_check" | "cargo_test";
  cwd: string;
};
type ChangeSet = {
  summary: string;
  files: FileChange[];
  recommended_checks: RecommendedCheck[];
  notes: string[];
};
type Review = { verdict: "approve" | "changes_requested"; summary: string };
type TeamResult = {
  task_id: string;
  status: string;
  stop_reason: string;
  plan: AgentPlan;
  changes?: ChangeSet | null;
  review?: Review | null;
};
type ChatResult = { content: string; model: string; provider: string };
type ToolRead = { tool: string; result: Record<string, unknown> };
type ToolProposal = { approval_id: string; expires_in_seconds: number };
type ToolExecution = { tool: string; result: Record<string, unknown> };
type VoiceTranscription = { text: string; engine: string; model: string; language: string };
type CheckResult = { label: string; passed: boolean; output: string };
type ProposalState = {
  taskId: string;
  status: string;
  changes: ChangeSet;
  review: Review | null;
  checkpointId: string;
  applied: boolean;
  checks: CheckResult[];
};
type Command = { label: string; hint: string; run: () => void };

const CONVERSATION_ID = "genesis-workbench";
const MODES: Mode[] = ["ask", "plan", "build", "review"];
const TARGET_SAMPLE_RATE = 16000;

function mergeBuffers(buffers: Float32Array[]) {
  const total = buffers.reduce((sum, item) => sum + item.length, 0);
  const merged = new Float32Array(total);
  let offset = 0;
  for (const buffer of buffers) {
    merged.set(buffer, offset);
    offset += buffer.length;
  }
  return merged;
}

function downsample(buffer: Float32Array, inputRate: number, outputRate: number) {
  if (inputRate === outputRate) return buffer;
  if (outputRate > inputRate) throw new Error("Output sample rate must not exceed input sample rate");
  const ratio = inputRate / outputRate;
  const length = Math.max(1, Math.round(buffer.length / ratio));
  const result = new Float32Array(length);
  let inputOffset = 0;
  for (let i = 0; i < length; i += 1) {
    const nextOffset = Math.min(buffer.length, Math.round((i + 1) * ratio));
    let sum = 0;
    let count = 0;
    for (let j = inputOffset; j < nextOffset; j += 1) {
      sum += buffer[j];
      count += 1;
    }
    result[i] = count ? sum / count : 0;
    inputOffset = nextOffset;
  }
  return result;
}

function encodeWav(samples: Float32Array, sampleRate: number) {
  const bytesPerSample = 2;
  const dataSize = samples.length * bytesPerSample;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);
  const writeAscii = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i += 1) view.setUint8(offset + i, value.charCodeAt(i));
  };
  writeAscii(0, "RIFF");
  view.setUint32(4, 36 + dataSize, true);
  writeAscii(8, "WAVE");
  writeAscii(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * bytesPerSample, true);
  view.setUint16(32, bytesPerSample, true);
  view.setUint16(34, 16, true);
  writeAscii(36, "data");
  view.setUint32(40, dataSize, true);
  let offset = 44;
  for (const sample of samples) {
    const clamped = Math.max(-1, Math.min(1, sample));
    view.setInt16(offset, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
    offset += 2;
  }
  return new Blob([buffer], { type: "audio/wav" });
}

function planText(plan: AgentPlan) {
  return [
    plan.goal,
    "",
    ...plan.steps.flatMap((step) => [`${step.id}. ${step.title}`, `   ${step.description}`]),
    ...(plan.notes.length ? ["", ...plan.notes.map((note) => `Note: ${note}`)] : []),
  ].join("\n");
}

function teamText(result: TeamResult) {
  const lines = [result.stop_reason];
  if (result.changes) {
    lines.push("", result.changes.summary);
    for (const file of result.changes.files) lines.push(`${file.action} ${file.path}${file.reason ? ` — ${file.reason}` : ""}`);
  }
  if (result.review) lines.push("", `Review: ${result.review.verdict}`, result.review.summary);
  return lines.join("\n");
}

async function readTool(tool: string, arguments_: Record<string, unknown> = {}) {
  return api<ToolRead>("/v1/tools/read", {
    method: "POST",
    body: JSON.stringify({ tool, arguments: arguments_ }),
  });
}

async function approvedMutation(tool: string, arguments_: Record<string, unknown>) {
  const proposal = await api<ToolProposal>("/v1/tools/propose", {
    method: "POST",
    body: JSON.stringify({ tool, arguments: arguments_ }),
  });
  return api<ToolExecution>("/v1/tools/execute", {
    method: "POST",
    body: JSON.stringify({ approval_id: proposal.approval_id, approved: true }),
  });
}

export default function WorkbenchHome() {
  const router = useRouter();
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<Mode>("ask");
  const [proposal, setProposal] = useState<ProposalState | null>(null);
  const [busy, setBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const [palette, setPalette] = useState(false);
  const [error, setError] = useState("");

  const streamRef = useRef<MediaStream | null>(null);
  const contextRef = useRef<AudioContext | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const chunksRef = useRef<Float32Array[]>([]);
  const sampleRateRef = useRef(48000);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    void api<WorkspaceList>("/v1/workspaces")
      .then((result) => setWorkspace(result.current))
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  useEffect(() => {
    const onKey = (event: globalThis.KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPalette((value) => !value);
      }
      if ((event.ctrlKey || event.metaKey) && event.key === ".") {
        event.preventDefault();
        setMode((current) => MODES[(MODES.indexOf(current) + 1) % MODES.length]);
      }
      if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.code === "Space") {
        event.preventDefault();
        if (recording) void stopRecording();
        else void startRecording();
      }
      if (event.key === "Escape") setPalette(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  function appendAssistant(content: string, meta?: string) {
    setTurns((items) => [...items, { role: "assistant", content, meta }]);
  }

  async function runAsk(history: Turn[]) {
    const lastUser = [...history].reverse().find((turn) => turn.role === "user");
    let contextFiles: string[] = [];
    let projectContext = "";
    if (lastUser?.content) {
      try {
        const selected = await readTool("project.context_read", {
          query: lastUser.content,
          max_files: 10,
          max_total_chars: 60_000,
        });
        contextFiles = Array.isArray(selected.result.files)
          ? selected.result.files.filter((value): value is string => typeof value === "string")
          : [];
        projectContext = typeof selected.result.content === "string" ? selected.result.content : "";
      } catch {
        // Project context is an enhancement. Chat remains available if indexing fails.
      }
    }

    setTurns([...history, { role: "assistant", content: "", meta: "streaming", context: contextFiles }]);
    const messages = history.map(({ role, content }) => ({ role, content }));
    if (projectContext && contextFiles.length) {
      messages.unshift({
        role: "system",
        content: `Genesis selected these current project files as bounded context: ${contextFiles.join(", ")}\n\n${projectContext}`,
      });
    }

    await streamApi(
      "/v1/chat/stream",
      {
        conversation_id: CONVERSATION_ID,
        use_memory: true,
        messages,
      },
      (message) => {
        if (message.event === "delta") {
          setTurns((current) => {
            const copy = [...current];
            const last = copy[copy.length - 1];
            if (last?.role === "assistant") copy[copy.length - 1] = { ...last, content: last.content + message.data.text };
            return copy;
          });
        }
        if (message.event === "meta") {
          setTurns((current) => {
            const copy = [...current];
            const last = copy[copy.length - 1];
            if (last?.role === "assistant") {
              const contextMeta = contextFiles.length ? ` · context ${contextFiles.length}` : "";
              copy[copy.length - 1] = { ...last, meta: `${message.data.provider} · ${message.data.model}${contextMeta}` };
            }
            return copy;
          });
        }
        if (message.event === "error") throw new Error(message.data.message);
      },
    );
  }

  async function runPlan(text: string) {
    const result = await api<AgentPlan>("/v1/agent/plan", {
      method: "POST",
      body: JSON.stringify({ task: text }),
    });
    appendAssistant(planText(result), "plan · indexed project");
  }

  async function runBuild(text: string) {
    setProposal(null);
    const result = await api<TeamResult>("/v1/team/run", {
      method: "POST",
      body: JSON.stringify({ task: text, max_agent_calls: 4, use_research: false, research_max_results: 8 }),
    });
    appendAssistant(teamText(result), `${result.status} · task ${result.task_id.slice(0, 8)}`);
    if (result.changes?.files.length) {
      setProposal({
        taskId: result.task_id,
        status: result.status,
        changes: result.changes,
        review: result.review ?? null,
        checkpointId: "",
        applied: false,
        checks: [],
      });
    }
  }

  async function runReview(text: string) {
    const diffResult = await readTool("git.diff");
    const diff = String(diffResult.result.output ?? "");
    if (!diff.trim()) throw new Error("There is no current Git diff to review.");
    const result = await api<ChatResult>("/v1/chat", {
      method: "POST",
      body: JSON.stringify({
        conversation_id: "genesis-diff-review",
        use_memory: false,
        messages: [
          { role: "system", content: "You are a read-only code reviewer. Review the Git diff for correctness, regressions, security issues, missing tests, and unnecessary complexity. Be concrete and prioritize blocking issues." },
          { role: "user", content: `REVIEW FOCUS:\n${text}\n\nGIT DIFF:\n${diff.slice(0, 120_000)}` },
        ],
      }),
    });
    appendAssistant(result.content, `review · ${result.provider} · ${result.model}`);
  }

  async function submit() {
    const text = input.trim();
    if (!text || busy) return;
    setBusy(true);
    setError("");
    setInput("");
    const history = [...turns, { role: "user" as const, content: text }];
    setTurns(history);
    try {
      if (mode === "ask") await runAsk(history);
      if (mode === "plan") await runPlan(text);
      if (mode === "build") await runBuild(text);
      if (mode === "review") await runReview(text);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }

  async function applyProposal() {
    if (!proposal || proposal.applied || busy) return;
    if (proposal.review?.verdict === "changes_requested") {
      const proceed = window.confirm("The reviewer requested changes. Apply this proposal anyway? Genesis will still create an undo checkpoint.");
      if (!proceed) return;
    }
    setBusy(true);
    setError("");
    try {
      const execution = await approvedMutation("workspace.apply_changes", {
        changes: proposal.changes.files.map(({ path, action, content }) => ({ path, action, content })),
      });
      const checkpointId = String(execution.result.checkpoint_id ?? "");
      if (!checkpointId) throw new Error("Genesis applied the changes but did not return an undo checkpoint.");
      setProposal((current) => current ? { ...current, applied: true, checkpointId, checks: [] } : current);
      appendAssistant(
        `Applied ${proposal.changes.files.length} file change${proposal.changes.files.length === 1 ? "" : "s"}. A conflict-safe undo checkpoint is active.`,
        `checkpoint ${checkpointId.slice(0, 8)}`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function runProposalChecks() {
    if (!proposal?.applied || busy) return;
    setBusy(true);
    setError("");
    setProposal((current) => current ? { ...current, checks: [] } : current);
    try {
      let checks = proposal.changes.recommended_checks;
      if (!checks.length) {
        const detected = await readTool("project.detect_checks");
        checks = Array.isArray(detected.result.checks) ? detected.result.checks as RecommendedCheck[] : [];
      }
      if (!checks.length) {
        appendAssistant("No supported project checks were detected for this workspace.", "checks");
        return;
      }

      const completed: CheckResult[] = [];
      for (const check of checks) {
        const execution = await approvedMutation("project.run_check", {
          kind: check.kind,
          cwd: check.cwd,
          timeout_seconds: 300,
        });
        const passed = Boolean(execution.result.passed);
        const output = String(execution.result.output ?? `exit ${String(execution.result.exit_code ?? "?")}`);
        completed.push({ label: `${check.kind} · ${check.cwd}`, passed, output });
        setProposal((current) => current ? { ...current, checks: [...completed] } : current);
        if (!passed) break;
      }
      const allPassed = completed.length > 0 && completed.every((item) => item.passed);
      appendAssistant(
        allPassed ? `All ${completed.length} project check${completed.length === 1 ? "" : "s"} passed.` : "A project check failed. The undo checkpoint is still available.",
        allPassed ? "checks passed" : "check failed",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function undoProposal() {
    if (!proposal?.applied || !proposal.checkpointId || busy) return;
    if (!window.confirm("Undo only the files Genesis changed in this proposal? Undo will refuse if any of those files were edited after Apply.")) return;
    setBusy(true);
    setError("");
    try {
      await approvedMutation("workspace.undo_changes", { checkpoint_id: proposal.checkpointId });
      const restored = proposal.changes.files.length;
      setProposal((current) => current ? { ...current, applied: false, checkpointId: "", checks: [] } : current);
      appendAssistant(`Undo restored ${restored} file${restored === 1 ? "" : "s"} to their exact pre-apply state.`, "undo complete");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  function onComposerKeyDown(event: ReactKeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void submit();
    }
  }

  function cycleMode() {
    setMode((current) => MODES[(MODES.indexOf(current) + 1) % MODES.length]);
  }

  async function startRecording() {
    if (recording || busy) return;
    setError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
      const context = new AudioContext();
      const source = context.createMediaStreamSource(stream);
      const processor = context.createScriptProcessor(4096, 1, 1);
      const silent = context.createGain();
      silent.gain.value = 0;
      chunksRef.current = [];
      sampleRateRef.current = context.sampleRate;
      processor.onaudioprocess = (event) => chunksRef.current.push(new Float32Array(event.inputBuffer.getChannelData(0)));
      source.connect(processor);
      processor.connect(silent);
      silent.connect(context.destination);
      streamRef.current = stream;
      contextRef.current = context;
      sourceRef.current = source;
      processorRef.current = processor;
      setRecording(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function stopRecording() {
    if (!recording) return;
    setRecording(false);
    setBusy(true);
    setError("");
    try {
      processorRef.current?.disconnect();
      sourceRef.current?.disconnect();
      streamRef.current?.getTracks().forEach((track) => track.stop());
      await contextRef.current?.close();
      const merged = mergeBuffers(chunksRef.current);
      if (!merged.length) throw new Error("No microphone audio was captured");
      const wav = encodeWav(downsample(merged, sampleRateRef.current, TARGET_SAMPLE_RATE), TARGET_SAMPLE_RATE);
      const response = await genesisFetch("/v1/voice/transcribe?language=auto", {
        method: "POST",
        headers: { "Content-Type": "audio/wav" },
        body: wav,
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload?.detail ?? `Voice request failed: ${response.status}`);
      const result = payload as VoiceTranscription;
      setInput((current) => current ? `${current.trimEnd()} ${result.text}` : result.text);
      requestAnimationFrame(() => inputRef.current?.focus());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      streamRef.current = null;
      contextRef.current = null;
      sourceRef.current = null;
      processorRef.current = null;
      chunksRef.current = [];
      setBusy(false);
    }
  }

  const commands: Command[] = [
    { label: "Ask", hint: "conversation · Ctrl .", run: () => setMode("ask") },
    { label: "Plan", hint: "read-only exploration", run: () => setMode("plan") },
    { label: "Build", hint: "architect → builder → reviewer", run: () => setMode("build") },
    { label: "Review", hint: "current Git diff", run: () => setMode("review") },
    { label: recording ? "Stop voice capture" : "Start voice capture", hint: "Ctrl Shift Space", run: () => recording ? void stopRecording() : void startRecording() },
    { label: "Open Projects", hint: "workspace & context", run: () => router.push("/projects") },
    { label: "Open Activity", hint: "tasks & evidence", run: () => router.push("/activity") },
    { label: "Open Settings", hint: "models, voice, memory, advanced", run: () => router.push("/settings") },
  ];

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <div className={styles.project}>
          <strong>{workspace?.name ?? "Genesis"}</strong>
          <span title={workspace?.path}>{workspace?.path ?? "Loading workspace…"}</span>
        </div>
        <div className={styles.state}>
          <span className={`${styles.stateDot} ${busy || recording ? styles.stateDotBusy : ""}`} />
          {recording ? "listening" : busy ? "working" : "ready"}
        </div>
      </header>

      {error ? <div className={styles.error} role="alert">{error}</div> : null}

      <section className={styles.feed} aria-live="polite">
        {turns.length === 0 ? (
          <div className={styles.empty}>
            <div className={styles.emptyInner}>
              <h1>What are we doing?</h1>
              <p>Type and press Enter, speak with the microphone, or press Ctrl+K. Genesis keeps the project, memory, tools and approvals underneath the conversation instead of making you operate the machinery.</p>
            </div>
          </div>
        ) : turns.map((turn, index) => (
          <article className={styles.turn} key={`${turn.role}-${index}`}>
            <div className={styles.role}>{turn.role === "user" ? "You" : "Genesis"}</div>
            <div>
              <p className={styles.content}>{turn.content || (busy ? "Working…" : "")}</p>
              {turn.meta || turn.context?.length ? (
                <div className={styles.meta}>
                  {turn.meta ? <span className={styles.pill}>{turn.meta}</span> : null}
                  {turn.context?.slice(0, 8).map((path) => <span className={styles.pill} key={path} title="Project context used">{path}</span>)}
                  {(turn.context?.length ?? 0) > 8 ? <span className={styles.pill}>+{(turn.context?.length ?? 0) - 8}</span> : null}
                </div>
              ) : null}
            </div>
          </article>
        ))}

        {proposal ? (
          <section className={styles.proposal} aria-label="Genesis proposed changes">
            <div className={styles.proposalHeader}>
              <strong>{proposal.changes.summary}</strong>
              <span>{proposal.review ? `review · ${proposal.review.verdict}` : proposal.status}</span>
            </div>
            <div className={styles.fileList}>
              {proposal.changes.files.map((file) => (
                <div className={styles.fileRow} key={file.path}>
                  <span>{file.path}</span><span>{file.action}</span>
                </div>
              ))}
            </div>
            <div className={styles.proposalActions}>
              {!proposal.applied ? (
                <button className={styles.actionButton} type="button" onClick={() => void applyProposal()} disabled={busy}>
                  {proposal.review?.verdict === "changes_requested" ? "Apply anyway…" : "Apply changes"}
                </button>
              ) : (
                <>
                  <button className={styles.actionButton} type="button" onClick={() => void runProposalChecks()} disabled={busy}>Run checks</button>
                  <button className={styles.dangerButton} type="button" onClick={() => void undoProposal()} disabled={busy}>Undo</button>
                </>
              )}
              <span className={styles.actionNote}>
                {proposal.applied
                  ? `Checkpoint ${proposal.checkpointId.slice(0, 8)} · undo refuses to overwrite later edits`
                  : "Nothing is written until you approve Apply."}
              </span>
            </div>
            {proposal.checks.length ? (
              <div className={styles.checkList}>
                {proposal.checks.map((check) => (
                  <div className={`${styles.checkResult} ${check.passed ? styles.checkPass : styles.checkFail}`} key={check.label}>
                    {check.passed ? "✓" : "✗"} {check.label}\n{check.output.slice(0, 4000)}
                  </div>
                ))}
              </div>
            ) : null}
          </section>
        ) : null}
      </section>

      <div className={styles.composerDock}>
        <div className={styles.composer}>
          <textarea
            ref={inputRef}
            className={styles.textarea}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={onComposerKeyDown}
            placeholder={recording ? "Listening…" : "Ask Genesis anything…"}
            aria-label="Ask Genesis"
            disabled={busy && !recording}
            rows={3}
          />
          <div className={styles.composerBar}>
            <button className={styles.modeButton} type="button" onClick={cycleMode} disabled={busy} title="Cycle mode (Ctrl+.)">{mode}</button>
            <button
              className={`${styles.iconButton} ${recording ? styles.iconButtonRecording : ""}`}
              type="button"
              onClick={() => recording ? void stopRecording() : void startRecording()}
              disabled={busy && !recording}
              aria-label={recording ? "Stop voice capture" : "Start voice capture"}
              title="Voice (Ctrl+Shift+Space)"
            >
              {recording ? "■" : "●"}
            </button>
            <button className={styles.iconButton} type="button" onClick={() => setPalette(true)} aria-label="Open command palette" title="Commands (Ctrl+K)">⌘</button>
            <span className={styles.shortcut}>Enter to run · Shift+Enter newline</span>
            <button className={styles.submitButton} type="button" onClick={() => void submit()} disabled={busy || !input.trim()} aria-label="Run request" title="Run request">↵</button>
          </div>
        </div>
      </div>

      {palette ? (
        <div className={styles.paletteBackdrop} role="presentation" onMouseDown={() => setPalette(false)}>
          <div className={styles.palette} role="dialog" aria-modal="true" aria-label="Genesis commands" onMouseDown={(event) => event.stopPropagation()}>
            <div className={styles.paletteTitle}>Commands</div>
            {commands.map((command) => (
              <button key={command.label} className={styles.command} type="button" onClick={() => { setPalette(false); command.run(); }}>
                <span>{command.label}</span><small>{command.hint}</small>
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </main>
  );
}
