"use client";

import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { useRouter } from "next/navigation";
import { api, genesisFetch, streamApi } from "../lib/api";
import styles from "./workbench-shell.module.css";

type Mode = "ask" | "plan" | "build" | "review";
type Turn = { role: "user" | "assistant"; content: string; meta?: string };
type Workspace = { name: string; path: string; is_git: boolean; selected: boolean };
type WorkspaceList = { current: Workspace; candidates: Workspace[] };
type AgentPlan = {
  goal: string;
  steps: Array<{ id: number; title: string; description: string; tool?: string | null }>;
  notes: string[];
};
type TeamResult = {
  task_id: string;
  status: string;
  stop_reason: string;
  plan: AgentPlan;
  changes?: { summary: string; files: Array<{ path: string; action: string; reason?: string }> } | null;
  review?: { verdict: string; summary: string } | null;
};
type ChatResult = { content: string; model: string; provider: string };
type ToolRead = { tool: string; result: Record<string, unknown> };
type VoiceTranscription = { text: string; engine: string; model: string; language: string };

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

export default function WorkbenchHome() {
  const router = useRouter();
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<Mode>("ask");
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

  async function runAsk(text: string, history: Turn[]) {
    setTurns([...history, { role: "assistant", content: "", meta: "streaming" }]);
    await streamApi(
      "/v1/chat/stream",
      {
        conversation_id: CONVERSATION_ID,
        use_memory: true,
        messages: history.map(({ role, content }) => ({ role, content })),
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
            if (last?.role === "assistant") copy[copy.length - 1] = { ...last, meta: `${message.data.provider} · ${message.data.model}` };
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
    appendAssistant(planText(result), "plan · read-only");
  }

  async function runBuild(text: string) {
    const result = await api<TeamResult>("/v1/team/run", {
      method: "POST",
      body: JSON.stringify({ task: text, max_agent_calls: 4, use_research: false, research_max_results: 8 }),
    });
    appendAssistant(teamText(result), `${result.status} · task ${result.task_id.slice(0, 8)}`);
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
      if (mode === "ask") await runAsk(text, history);
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
              {turn.meta ? <div className={styles.meta}><span className={styles.pill}>{turn.meta}</span></div> : null}
            </div>
          </article>
        ))}
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
