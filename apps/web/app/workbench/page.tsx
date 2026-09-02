"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../../lib/api";
import TerminalPane from "./TerminalPane";
import styles from "./workbench.module.css";

const Editor = dynamic(() => import("@monaco-editor/react"), { ssr: false });

type FileItem = { path: string; type: "file" | "dir"; size: number | null };
type Check = { kind: string; cwd: string };
type Task = { id: string; title: string; status: string; stop_reason?: string | null };
type Worker = { name: string; type: string; detail: string };
type ToolRead = { tool: string; result: Record<string, unknown> };
type Proposal = { approval_id: string; tool: string; arguments: Record<string, unknown>; expires_in_seconds: number };
type Execution = { tool: string; result: Record<string, unknown> };
type AgentMode = "plan" | "build" | "fix" | "review";
type AgentPlan = {
  goal: string;
  steps: Array<{ id: number; title: string; description: string; tool?: string | null }>;
  notes: string[];
};
type ChatResult = { content: string; model: string; provider: string };
type TeamResult = {
  task_id: string;
  status: string;
  stop_reason: string;
  changes?: { summary: string; files: Array<{ path: string; action: string; reason?: string }> } | null;
  review?: { verdict: string; summary: string } | null;
};

const MODE_HELP: Record<AgentMode, string> = {
  plan: "Planner only · no Builder call",
  build: "Architect → Builder → Reviewer",
  fix: "Bounded minimal-repair team",
  review: "Read-only review of current Git diff",
};

function languageFor(path: string) {
  const ext = path.split(".").pop()?.toLowerCase();
  return ({
    ts: "typescript", tsx: "typescript", js: "javascript", jsx: "javascript", py: "python", rs: "rust",
    json: "json", css: "css", md: "markdown", yml: "yaml", yaml: "yaml", toml: "toml", sh: "shell", ps1: "powershell",
  } as Record<string, string>)[ext ?? ""] ?? "plaintext";
}

async function readTool(tool: string, arguments_: Record<string, unknown> = {}) {
  return api<ToolRead>("/v1/tools/read", {
    method: "POST",
    body: JSON.stringify({ tool, arguments: arguments_ }),
  });
}

async function approvedMutation(tool: string, arguments_: Record<string, unknown>, description: string) {
  const proposal = await api<Proposal>("/v1/tools/propose", {
    method: "POST",
    body: JSON.stringify({ tool, arguments: arguments_ }),
  });
  if (!window.confirm(`${description}\n\nTool: ${tool}\nApproval expires in ${proposal.expires_in_seconds}s.`)) {
    throw new Error("Approval cancelled by user");
  }
  return api<Execution>("/v1/tools/execute", {
    method: "POST",
    body: JSON.stringify({ approval_id: proposal.approval_id, approved: true }),
  });
}

function settledValue<T>(result: PromiseSettledResult<T>): T | null {
  return result.status === "fulfilled" ? result.value : null;
}

function teamSummary(result: TeamResult) {
  const lines = [`task: ${result.task_id}`, `status: ${result.status}`, result.stop_reason];
  if (result.changes) {
    lines.push("", result.changes.summary);
    for (const file of result.changes.files) {
      lines.push(`${file.action} ${file.path}${file.reason ? ` — ${file.reason}` : ""}`);
    }
  }
  if (result.review) lines.push("", `review: ${result.review.verdict}`, result.review.summary);
  return lines.join("\n");
}

function planSummary(plan: AgentPlan) {
  const lines = [`goal: ${plan.goal}`];
  for (const step of plan.steps) {
    lines.push(`${step.id}. ${step.title}${step.tool ? ` [${step.tool}]` : ""}`, `   ${step.description}`);
  }
  if (plan.notes.length) lines.push("", ...plan.notes.map((note) => `note: ${note}`));
  return lines.join("\n");
}

export default function WorkbenchPage() {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [selected, setSelected] = useState("");
  const [content, setContent] = useState("");
  const [savedContent, setSavedContent] = useState("");
  const [checks, setChecks] = useState<Check[]>([]);
  const [selectedCheck, setSelectedCheck] = useState("");
  const [tasks, setTasks] = useState<Task[]>([]);
  const [workers, setWorkers] = useState<Worker[]>([]);
  const [agentMode, setAgentMode] = useState<AgentMode>("build");
  const [agentTask, setAgentTask] = useState("Inspect this workspace and propose the highest-value code improvement. Do not apply changes automatically.");
  const [agentResult, setAgentResult] = useState("");
  const [gitStatus, setGitStatus] = useState("");
  const [gitDiff, setGitDiff] = useState("");
  const [terminalOutput, setTerminalOutput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const dirty = content !== savedContent;
  const fileOnly = useMemo(() => files.filter((item) => item.type === "file"), [files]);
  const projectSnapshot = useMemo(() => {
    const extensions = new Map<string, number>();
    for (const file of fileOnly) {
      const name = file.path.split("/").pop() ?? file.path;
      const ext = name.includes(".") ? name.split(".").pop()?.toLowerCase() || "other" : "other";
      extensions.set(ext, (extensions.get(ext) ?? 0) + 1);
    }
    const dominant = [...extensions.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 4)
      .map(([ext, count]) => `${ext}:${count}`)
      .join(" · ");
    const branch = gitStatus.split("\n")[0]?.trim() || "Git unavailable";
    const detectedChecks = checks.length ? checks.map((item) => item.kind).join(", ") : "none detected";
    return [`${fileOnly.length} source files`, dominant || "no extensions yet", branch, `checks: ${detectedChecks}`].join("\n");
  }, [fileOnly, checks, gitStatus]);

  const refresh = useCallback(async () => {
    setError("");
    try {
      const fileResult = await readTool("workspace.list", { path: ".", recursive: true });
      setFiles(((fileResult.result.items as FileItem[]) ?? []).sort((a, b) => a.path.localeCompare(b.path)));

      const [statusSettled, diffSettled, checkSettled, taskSettled, workerSettled] = await Promise.allSettled([
        readTool("git.status"),
        readTool("git.diff"),
        readTool("project.detect_checks"),
        api<Task[]>("/v1/tasks?limit=20"),
        api<Worker[]>("/v1/workers"),
      ]);
      const statusResult = settledValue(statusSettled);
      const diffResult = settledValue(diffSettled);
      const checkResult = settledValue(checkSettled);
      setGitStatus(String(statusResult?.result.output ?? "Not a Git repository or Git unavailable."));
      setGitDiff(String(diffResult?.result.output ?? ""));
      const nextChecks = (checkResult?.result.checks as Check[] | undefined) ?? [];
      setChecks(nextChecks);
      setSelectedCheck((current) => current || (nextChecks.length ? `${nextChecks[0].kind}|${nextChecks[0].cwd}` : ""));
      setTasks(settledValue(taskSettled) ?? []);
      setWorkers(settledValue(workerSettled) ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  async function openFile(path: string) {
    if (dirty && !window.confirm("Discard unsaved editor changes?")) return;
    setBusy(true); setError("");
    try {
      const result = await readTool("workspace.read", { path });
      const text = String(result.result.content ?? "");
      setSelected(path); setContent(text); setSavedContent(text);
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  }

  async function saveFile() {
    if (!selected || !dirty) return;
    setBusy(true); setError("");
    try {
      const result = await approvedMutation("workspace.write", { path: selected, content, overwrite: true }, `Approve replacing ${selected}?`);
      setSavedContent(content);
      setTerminalOutput(`Saved ${selected}\n${JSON.stringify(result.result, null, 2)}`);
      await refresh();
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  }

  async function runCheck() {
    if (!selectedCheck) return;
    const [kind, cwd] = selectedCheck.split("|");
    setBusy(true); setError("");
    try {
      const result = await approvedMutation(
        "project.run_check",
        { kind, cwd, timeout_seconds: 300 },
        `Approve running the fixed Genesis check ${kind} in ${cwd}?`,
      );
      const check = result.result as Record<string, unknown>;
      setTerminalOutput(
        `$ ${Array.isArray(check.command) ? check.command.join(" ") : kind}\n${String(check.output ?? "")}\n\n` +
        `exit=${String(check.exit_code ?? "?")} passed=${String(check.passed ?? false)}`,
      );
      await refresh();
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  }

  async function runGenesis() {
    if (!agentTask.trim() && agentMode !== "review") return;
    setBusy(true); setError(""); setAgentResult("Genesis is working…");
    try {
      if (agentMode === "plan") {
        const result = await api<AgentPlan>("/v1/agent/plan", {
          method: "POST",
          body: JSON.stringify({ task: agentTask.trim() }),
        });
        setAgentResult(planSummary(result));
      } else if (agentMode === "review") {
        if (!gitDiff.trim()) throw new Error("There is no current Git diff to review.");
        const diff = gitDiff.slice(0, 120_000);
        const result = await api<ChatResult>("/v1/chat", {
          method: "POST",
          body: JSON.stringify({
            conversation_id: "workbench-diff-review",
            use_memory: false,
            messages: [
              {
                role: "system",
                content: "You are a read-only code reviewer. Review the supplied Git diff for correctness, regressions, security issues, missing tests, and unnecessary complexity. Do not propose unrelated features. Be concrete and prioritize blocking issues.",
              },
              {
                role: "user",
                content: `REVIEW FOCUS:\n${agentTask.trim() || "Review the current changes."}\n\nGIT DIFF:\n${diff}`,
              },
            ],
          }),
        });
        setAgentResult(`read-only review · ${result.provider} / ${result.model}\n\n${result.content}`);
      } else {
        const task = agentMode === "fix"
          ? `Diagnose the root cause and propose the smallest safe fix for this request. Avoid unrelated refactors. Do not apply changes automatically.\n\nREQUEST:\n${agentTask.trim()}`
          : agentTask.trim();
        const result = await api<TeamResult>("/v1/team/run", {
          method: "POST",
          body: JSON.stringify({ task, max_agent_calls: 4, use_research: false, research_max_results: 8 }),
        });
        setAgentResult(teamSummary(result));
        await refresh();
      }
    } catch (err) {
      setAgentResult("");
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className={styles.page}>
      <div className={styles.toolbar}>
        <button onClick={() => void refresh()} disabled={busy}>Refresh</button>
        <button onClick={() => void saveFile()} disabled={busy || !dirty || !selected}>Save approved</button>
        <select value={selectedCheck} onChange={(event) => setSelectedCheck(event.target.value)}>
          {checks.map((check) => <option key={`${check.kind}|${check.cwd}`} value={`${check.kind}|${check.cwd}`}>{check.kind} · {check.cwd}</option>)}
        </select>
        <button onClick={() => void runCheck()} disabled={busy || !selectedCheck}>Run approved check</button>
        {error ? <span className={styles.error}>{error}</span> : null}
        <span className={styles.badge}>{dirty ? "UNSAVED" : selected ? "SAVED" : "NO FILE"} · fixed-command terminal</span>
      </div>

      <section className={styles.grid}>
        <aside className={styles.panel}>
          <div className={styles.panelHeader}><span>Explorer</span><span>{fileOnly.length}</span></div>
          <div className={styles.explorer}>
            {fileOnly.map((item) => (
              <button key={item.path} className={`${styles.fileButton} ${selected === item.path ? styles.selected : ""}`} title={item.path} onClick={() => void openFile(item.path)}>{item.path}</button>
            ))}
          </div>
        </aside>

        <section className={styles.panel}>
          <div className={styles.panelHeader}><span>{selected || "Editor"}</span><span className={styles.editorMeta}>{selected ? languageFor(selected) : "plaintext"}</span></div>
          <div className={styles.editorWrap}>
            <Editor height="100%" theme="vs-dark" language={languageFor(selected)} value={content} onChange={(value) => setContent(value ?? "")} options={{ minimap: { enabled: false }, fontSize: 13, wordWrap: "off", automaticLayout: true, scrollBeyondLastLine: false, readOnly: !selected }} />
          </div>
        </section>

        <aside className={styles.panel} style={{ borderRight: 0 }}>
          <div className={styles.panelHeader}><span>Genesis AI</span><span>{tasks.length} tasks</span></div>
          <div className={styles.sideContent}>
            <div className={styles.card}>
              <strong>Project snapshot</strong>
              <div className={styles.projectSnapshot}>{projectSnapshot}</div>
            </div>
            <div className={styles.card}>
              <strong>Ask Genesis</strong>
              <div className={styles.modeRow}>
                {(["plan", "build", "fix", "review"] as AgentMode[]).map((mode) => (
                  <button
                    key={mode}
                    className={`${styles.modeButton} ${agentMode === mode ? styles.modeActive : ""}`}
                    onClick={() => setAgentMode(mode)}
                    disabled={busy}
                    aria-pressed={agentMode === mode}
                  >
                    {mode[0].toUpperCase() + mode.slice(1)}
                  </button>
                ))}
              </div>
              <textarea className={styles.aiBox} value={agentTask} onChange={(event) => setAgentTask(event.target.value)} disabled={busy} />
              <div className={styles.aiActions}>
                <button className={styles.aiButton} onClick={() => void runGenesis()} disabled={busy || (!agentTask.trim() && agentMode !== "review")}>Run {agentMode}</button>
                <small>{MODE_HELP[agentMode]}</small>
              </div>
              {agentResult ? <div className={styles.aiResult}>{agentResult}</div> : null}
            </div>
            <div className={styles.card}><strong>Workers</strong>{workers.map((worker) => <small key={worker.name}>{worker.name} · {worker.type}<br /></small>)}</div>
            {tasks.map((task) => <div className={styles.card} key={task.id}><strong>{task.title}</strong><small>{task.status}{task.stop_reason ? ` · ${task.stop_reason}` : ""}</small></div>)}
          </div>
        </aside>

        <section className={`${styles.panel} ${styles.bottomLeft}`}>
          <div className={styles.panelHeader}><span>Check output</span><span>stdin disabled</span></div>
          <div className={styles.terminalWrap}><TerminalPane output={terminalOutput} /></div>
        </section>

        <section className={`${styles.panel} ${styles.bottomRight}`}>
          <div className={styles.panelHeader}><span>Git diff</span><span>{gitDiff ? "changes" : ""}</span></div>
          <div className={styles.sideContent}><pre className={styles.pre}>{gitStatus ? `${gitStatus}\n\n` : ""}{gitDiff || "No unstaged diff."}</pre></div>
        </section>
      </section>
    </main>
  );
}
