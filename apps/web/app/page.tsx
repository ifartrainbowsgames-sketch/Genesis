"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, streamApi } from "../lib/api";

type Provider = "ollama" | "openai" | "anthropic";
type ChatLine = { role: "user" | "assistant"; content: string };
type Plan = {
  goal: string;
  steps: Array<{ id: number; title: string; description: string; tool?: string | null; arguments?: Record<string, unknown> }>;
  notes: string[];
};
type FileChange = { path: string; action: "create" | "replace"; content: string; reason: string };
type RecommendedCheck = {
  kind: "python_compile" | "python_test" | "npm_build" | "npm_test" | "cargo_check" | "cargo_test";
  cwd: string;
};
type ChangeSet = { summary: string; files: FileChange[]; recommended_checks: RecommendedCheck[]; notes: string[] };
type ToolProposal = { approval_id: string };
type ToolResult = { tool: string; result: unknown };
type Activity = { label: string; detail: string; ok: boolean };
type Workspace = { name: string; path: string; is_git: boolean; selected: boolean };
type WorkspaceList = { current: Workspace; candidates: Workspace[] };
type MemoryItem = { id: string; conversation_id: string; role: string; content: string; created_at?: string | null };

const CONVERSATION_ID = "genesis-main";

export default function Home() {
  const [provider, setProvider] = useState<Provider>("ollama");
  const [model, setModel] = useState("");
  const [chatInput, setChatInput] = useState("");
  const [taskInput, setTaskInput] = useState("");
  const [chat, setChat] = useState<ChatLine[]>([]);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [changes, setChanges] = useState<ChangeSet | null>(null);
  const [activity, setActivity] = useState<Activity[]>([]);
  const [workspaces, setWorkspaces] = useState<WorkspaceList | null>(null);
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [memoryQuery, setMemoryQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const status = useMemo(() => (busy ? "working" : "ready"), [busy]);

  useEffect(() => {
    void refreshWorkspaces();
    void refreshMemory();
  }, []);

  function fail(err: unknown) {
    setError(err instanceof Error ? err.message : String(err));
  }

  function log(label: string, detail: string, ok = true) {
    setActivity((items) => [{ label, detail, ok }, ...items].slice(0, 80));
  }

  async function refreshWorkspaces() {
    try {
      setWorkspaces(await api<WorkspaceList>("/v1/workspaces"));
    } catch (err) {
      fail(err);
    }
  }

  async function selectWorkspace(path: string) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const selected = await api<Workspace>("/v1/workspaces/select", {
        method: "POST",
        body: JSON.stringify({ path }),
      });
      log("Workspace", `Selected ${selected.path}`);
      setPlan(null);
      setChanges(null);
      await refreshWorkspaces();
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  }

  async function refreshMemory(query = memoryQuery.trim()) {
    try {
      if (query) {
        const result = await api<MemoryItem[]>("/v1/memory/search", {
          method: "POST",
          body: JSON.stringify({ query, conversation_id: CONVERSATION_ID, limit: 30 }),
        });
        setMemories(result);
      } else {
        setMemories(await api<MemoryItem[]>(`/v1/memory?conversation_id=${encodeURIComponent(CONVERSATION_ID)}&limit=30`));
      }
    } catch (err) {
      fail(err);
    }
  }

  async function removeMemory(id: string) {
    try {
      const result = await api<{ deleted: boolean }>(`/v1/memory/${encodeURIComponent(id)}`, { method: "DELETE" });
      if (result.deleted) setMemories((items) => items.filter((item) => item.id !== id));
    } catch (err) {
      fail(err);
    }
  }

  async function clearConversationMemory() {
    if (!window.confirm("Delete Genesis memory for this conversation?")) return;
    try {
      const result = await api<{ deleted: number }>(`/v1/memory?conversation_id=${encodeURIComponent(CONVERSATION_ID)}`, { method: "DELETE" });
      setMemories([]);
      log("Memory", `Deleted ${result.deleted} record(s)`);
    } catch (err) {
      fail(err);
    }
  }

  async function sendChat(event: FormEvent) {
    event.preventDefault();
    const text = chatInput.trim();
    if (!text || busy) return;
    setError("");
    setBusy(true);
    setChatInput("");

    const history = [...chat, { role: "user" as const, content: text }];
    setChat([...history, { role: "assistant", content: "" }]);

    try {
      await streamApi(
        "/v1/chat/stream",
        {
          provider,
          model: model.trim() || null,
          conversation_id: CONVERSATION_ID,
          use_memory: true,
          messages: history,
        },
        (message) => {
          if (message.event === "delta") {
            setChat((current) => {
              const copy = [...current];
              const last = copy[copy.length - 1];
              if (last?.role === "assistant") copy[copy.length - 1] = { ...last, content: last.content + message.data.text };
              return copy;
            });
          }
          if (message.event === "meta") log("Model", `${message.data.provider} · ${message.data.model}`);
          if (message.event === "error") throw new Error(message.data.message);
        },
      );
      await refreshMemory("");
    } catch (err) {
      fail(err);
      setChat((current) => {
        const last = current[current.length - 1];
        if (last?.role === "assistant" && !last.content) return current.slice(0, -1);
        return current;
      });
    } finally {
      setBusy(false);
    }
  }

  async function makePlan(event: FormEvent) {
    event.preventDefault();
    const task = taskInput.trim();
    if (!task || busy) return;
    setError("");
    setBusy(true);
    setChanges(null);
    try {
      setPlan(await api<Plan>("/v1/agent/plan", {
        method: "POST",
        body: JSON.stringify({ task, provider, model: model.trim() || null }),
      }));
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  }

  async function generateChanges() {
    const task = taskInput.trim();
    if (!task || busy) return;
    setError("");
    setBusy(true);
    try {
      const result = await api<ChangeSet>("/v1/agent/build", {
        method: "POST",
        body: JSON.stringify({ task, provider, model: model.trim() || null }),
      });
      setChanges(result);
      log("Builder", `Proposed ${result.files.length} file change(s). Nothing applied yet.`);
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  }

  async function executeApprovedTool(tool: string, args: Record<string, unknown>): Promise<ToolResult> {
    const proposal = await api<ToolProposal>("/v1/tools/propose", {
      method: "POST",
      body: JSON.stringify({ tool, arguments: args }),
    });
    return api<ToolResult>("/v1/tools/execute", {
      method: "POST",
      body: JSON.stringify({ approval_id: proposal.approval_id, approved: true }),
    });
  }

  async function inspectGit(tool: "git.status" | "git.diff") {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const result = await executeApprovedTool(tool, {});
      const data = result.result as { output?: string };
      log(tool === "git.status" ? "Git status" : "Git diff", data.output || "Clean / no output");
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  }

  async function applyChanges() {
    if (!changes || changes.files.length === 0 || busy) return;
    setError("");
    setBusy(true);
    try {
      const result = await executeApprovedTool("workspace.apply_changes", {
        changes: changes.files.map(({ path, action, content }) => ({ path, action, content })),
      });
      log("Applied", JSON.stringify(result.result, null, 2));
      await inspectGitAfterApply();
    } catch (err) {
      fail(err);
      log("Apply failed", err instanceof Error ? err.message : String(err), false);
    } finally {
      setBusy(false);
    }
  }

  async function inspectGitAfterApply() {
    try {
      const result = await executeApprovedTool("git.diff", {});
      const data = result.result as { output?: string };
      log("Git diff after apply", data.output || "No diff available");
    } catch {
      // Workspace may not be a Git repository; applying files is still valid.
    }
  }

  async function runCheck(check: RecommendedCheck) {
    if (busy) return;
    setError("");
    setBusy(true);
    try {
      const result = await executeApprovedTool("project.run_check", { kind: check.kind, cwd: check.cwd, timeout_seconds: 180 });
      const data = result.result as { passed?: boolean; output?: string; exit_code?: number };
      log(`${check.kind} · ${data.passed ? "passed" : "failed"}`, data.output || `exit ${data.exit_code ?? "?"}`, Boolean(data.passed));
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <div className="eyebrow">LOCAL-FIRST AI WORKSTATION</div>
          <h1>Genesis</h1>
        </div>
        <div className="status"><span />{status}</div>
      </header>

      <section className="controlStrip panel">
        <label>
          Provider
          <select value={provider} onChange={(e) => setProvider(e.target.value as Provider)}>
            <option value="ollama">Ollama · local</option>
            <option value="openai">OpenAI · optional cloud</option>
            <option value="anthropic">Anthropic · optional cloud</option>
          </select>
        </label>
        <label>
          Model override
          <input value={model} onChange={(e) => setModel(e.target.value)} placeholder="default model" />
        </label>
        <div className="workspaceControl">
          <span className="fieldLabel">Workspace</span>
          <select
            value={workspaces?.current.path ?? ""}
            disabled={!workspaces || busy}
            onChange={(e) => void selectWorkspace(e.target.value)}
          >
            {workspaces?.candidates.map((item) => <option key={item.path} value={item.path}>{item.name}{item.is_git ? " · git" : ""}</option>)}
          </select>
          <small title={workspaces?.current.path}>{workspaces?.current.path ?? "loading workspace…"}</small>
        </div>
        <div className="gitButtons">
          <button type="button" disabled={busy} onClick={() => void inspectGit("git.status")}>Git status</button>
          <button type="button" disabled={busy} onClick={() => void inspectGit("git.diff")}>Git diff</button>
        </div>
      </section>

      {error && <div className="error">{error}</div>}

      <div className="mainGrid">
        <section className="panel chatPanel">
          <div className="panelTitle"><div><span>01</span> Chat</div><small>streaming · memory on</small></div>
          <div className="messages">
            {chat.length === 0 && <div className="empty">Talk to Genesis. Responses stream live and memory remains inspectable in your own database.</div>}
            {chat.map((line, index) => (
              <article key={index} className={`message ${line.role}`}>
                <b>{line.role === "user" ? "You" : "Genesis"}</b>
                <p>{line.content || (busy ? "▍" : "")}</p>
              </article>
            ))}
          </div>
          <form onSubmit={sendChat} className="composer">
            <textarea value={chatInput} onChange={(e) => setChatInput(e.target.value)} placeholder="Ask Genesis…" rows={3} />
            <button disabled={busy}>Send</button>
          </form>
        </section>

        <section className="panel plannerPanel">
          <div className="panelTitle"><div><span>02</span> Build</div><small>review → approve → apply</small></div>
          <form onSubmit={makePlan} className="plannerForm">
            <textarea value={taskInput} onChange={(e) => setTaskInput(e.target.value)} placeholder="Example: add authentication to this repository" rows={5} />
            <div className="buttonRow">
              <button disabled={busy}>Plan</button>
              <button type="button" disabled={busy || !taskInput.trim()} onClick={generateChanges}>Generate changes</button>
            </div>
          </form>
          <div className="plan">
            {!plan && !changes && <div className="empty">Select a repository, describe the job, inspect the plan, then approve exact file changes.</div>}
            {plan && (
              <div className="planBlock">
                <div className="sectionLabel">Plan</div><h2>{plan.goal}</h2>
                {plan.steps.map((step) => (
                  <article className="step" key={step.id}>
                    <div className="stepNo">{String(step.id).padStart(2, "0")}</div>
                    <div><h3>{step.title}</h3><p>{step.description}</p>{step.tool && <code>{step.tool} {JSON.stringify(step.arguments ?? {})}</code>}</div>
                  </article>
                ))}
              </div>
            )}
            {changes && (
              <div className="changesBlock">
                <div className="sectionLabel">Proposed change set</div><h2>{changes.summary}</h2>
                {changes.files.length === 0 && <div className="empty">Builder proposed no file changes.</div>}
                {changes.files.map((file) => (
                  <details className="fileChange" key={file.path}>
                    <summary><b>{file.action}</b> {file.path}</summary>
                    {file.reason && <p>{file.reason}</p>}<pre>{file.content}</pre>
                  </details>
                ))}
                {changes.files.length > 0 && <button className="approveButton" type="button" disabled={busy} onClick={applyChanges}>Approve & apply {changes.files.length} file{changes.files.length === 1 ? "" : "s"}</button>}
                {changes.recommended_checks.length > 0 && (
                  <div className="checks"><div className="sectionLabel">Recommended checks</div>
                    {changes.recommended_checks.map((check, index) => <button className="secondaryButton" type="button" key={`${check.kind}-${index}`} disabled={busy} onClick={() => runCheck(check)}>Run {check.kind} · {check.cwd}</button>)}
                  </div>
                )}
                {changes.notes?.length > 0 && <div className="notes">{changes.notes.join(" · ")}</div>}
              </div>
            )}
          </div>
        </section>

        <aside className="panel memoryPanel">
          <div className="panelTitle"><div><span>03</span> Memory</div><small>{memories.length} shown</small></div>
          <form className="memorySearch" onSubmit={(e) => { e.preventDefault(); void refreshMemory(); }}>
            <input value={memoryQuery} onChange={(e) => setMemoryQuery(e.target.value)} placeholder="Search memory" />
            <div className="buttonRow"><button>Search</button><button type="button" onClick={() => { setMemoryQuery(""); void refreshMemory(""); }}>Recent</button></div>
          </form>
          <div className="memoryList">
            {memories.length === 0 && <div className="empty">No persistent memories found yet.</div>}
            {memories.map((item) => (
              <article className="memoryItem" key={item.id}>
                <div className="memoryMeta"><b>{item.role}</b><button type="button" onClick={() => void removeMemory(item.id)}>delete</button></div>
                <p>{item.content}</p>
              </article>
            ))}
          </div>
          <button className="dangerButton" type="button" onClick={clearConversationMemory}>Clear conversation memory</button>
        </aside>
      </div>

      <section className="panel activityPanel">
        <div className="panelTitle"><div><span>04</span> Activity</div><small>models · tools · tests · git</small></div>
        <div className="activityList">
          {activity.length === 0 && <div className="empty">No activity yet.</div>}
          {activity.map((item, index) => (
            <article className={`activityItem ${item.ok ? "ok" : "bad"}`} key={index}><b>{item.label}</b><pre>{item.detail}</pre></article>
          ))}
        </div>
      </section>
    </main>
  );
}
