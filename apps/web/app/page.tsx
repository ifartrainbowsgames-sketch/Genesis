"use client";

import { FormEvent, useMemo, useState } from "react";
import { api } from "../lib/api";

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
type ChangeSet = {
  summary: string;
  files: FileChange[];
  recommended_checks: RecommendedCheck[];
  notes: string[];
};
type ToolProposal = { approval_id: string };
type ToolResult = { tool: string; result: unknown };
type Activity = { label: string; detail: string; ok: boolean };

export default function Home() {
  const [provider, setProvider] = useState<Provider>("ollama");
  const [model, setModel] = useState("");
  const [chatInput, setChatInput] = useState("");
  const [taskInput, setTaskInput] = useState("");
  const [chat, setChat] = useState<ChatLine[]>([]);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [changes, setChanges] = useState<ChangeSet | null>(null);
  const [activity, setActivity] = useState<Activity[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const status = useMemo(() => (busy ? "working" : "ready"), [busy]);

  function fail(err: unknown) {
    setError(err instanceof Error ? err.message : String(err));
  }

  async function sendChat(event: FormEvent) {
    event.preventDefault();
    const text = chatInput.trim();
    if (!text || busy) return;
    setError("");
    setBusy(true);
    setChatInput("");
    const nextChat = [...chat, { role: "user" as const, content: text }];
    setChat(nextChat);
    try {
      const response = await api<{ content: string }>("/v1/chat", {
        method: "POST",
        body: JSON.stringify({
          provider,
          model: model.trim() || null,
          conversation_id: "genesis-main",
          use_memory: true,
          messages: nextChat,
        }),
      });
      setChat((current) => [...current, { role: "assistant", content: response.content }]);
    } catch (err) {
      fail(err);
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
      const result = await api<Plan>("/v1/agent/plan", {
        method: "POST",
        body: JSON.stringify({ task, provider, model: model.trim() || null }),
      });
      setPlan(result);
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
      setActivity((items) => [
        { label: "Builder", detail: `Proposed ${result.files.length} file change(s). Nothing applied yet.`, ok: true },
        ...items,
      ]);
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

  async function applyChanges() {
    if (!changes || changes.files.length === 0 || busy) return;
    setError("");
    setBusy(true);
    try {
      const result = await executeApprovedTool("workspace.apply_changes", {
        changes: changes.files.map(({ path, action, content }) => ({ path, action, content })),
      });
      setActivity((items) => [
        { label: "Applied", detail: JSON.stringify(result.result), ok: true },
        ...items,
      ]);
    } catch (err) {
      fail(err);
      setActivity((items) => [{ label: "Apply failed", detail: err instanceof Error ? err.message : String(err), ok: false }, ...items]);
    } finally {
      setBusy(false);
    }
  }

  async function runCheck(check: RecommendedCheck) {
    if (busy) return;
    setError("");
    setBusy(true);
    try {
      const result = await executeApprovedTool("project.run_check", {
        kind: check.kind,
        cwd: check.cwd,
        timeout_seconds: 180,
      });
      const data = result.result as { passed?: boolean; output?: string; exit_code?: number };
      setActivity((items) => [
        {
          label: `${check.kind} · ${data.passed ? "passed" : "failed"}`,
          detail: data.output || `exit ${data.exit_code ?? "?"}`,
          ok: Boolean(data.passed),
        },
        ...items,
      ]);
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
          <div className="eyebrow">LOCAL-FIRST AI WORKSPACE</div>
          <h1>Genesis</h1>
        </div>
        <div className="status"><span />{status}</div>
      </header>

      <section className="controls panel">
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
          <input value={model} onChange={(e) => setModel(e.target.value)} placeholder="leave blank for default" />
        </label>
      </section>

      {error && <div className="error">{error}</div>}

      <div className="grid">
        <section className="panel chatPanel">
          <div className="panelTitle">
            <div><span>01</span> Chat</div>
            <small>memory on</small>
          </div>
          <div className="messages">
            {chat.length === 0 && <div className="empty">Talk to your model. With PostgreSQL running, conversation memory stays in your own database.</div>}
            {chat.map((line, index) => (
              <article key={index} className={`message ${line.role}`}>
                <b>{line.role === "user" ? "You" : "Genesis"}</b>
                <p>{line.content}</p>
              </article>
            ))}
          </div>
          <form onSubmit={sendChat} className="composer">
            <textarea value={chatInput} onChange={(e) => setChatInput(e.target.value)} placeholder="Ask Genesis…" rows={3} />
            <button disabled={busy}>Send</button>
          </form>
        </section>

        <section className="panel plannerPanel">
          <div className="panelTitle">
            <div><span>02</span> Build</div>
            <small>review → approve → apply</small>
          </div>
          <form onSubmit={makePlan} className="plannerForm">
            <textarea value={taskInput} onChange={(e) => setTaskInput(e.target.value)} placeholder="Example: Build a TypeScript notes API in my workspace" rows={5} />
            <div className="buttonRow">
              <button disabled={busy}>Plan</button>
              <button type="button" disabled={busy || !taskInput.trim()} onClick={generateChanges}>Generate changes</button>
            </div>
          </form>

          <div className="plan">
            {!plan && !changes && <div className="empty">Plan first, then generate concrete files. Genesis cannot apply its own proposal until you press the approval button.</div>}

            {plan && (
              <div className="planBlock">
                <div className="sectionLabel">Plan</div>
                <h2>{plan.goal}</h2>
                {plan.steps.map((step) => (
                  <article className="step" key={step.id}>
                    <div className="stepNo">{String(step.id).padStart(2, "0")}</div>
                    <div>
                      <h3>{step.title}</h3>
                      <p>{step.description}</p>
                      {step.tool && <code>{step.tool} {JSON.stringify(step.arguments ?? {})}</code>}
                    </div>
                  </article>
                ))}
              </div>
            )}

            {changes && (
              <div className="changesBlock">
                <div className="sectionLabel">Proposed change set</div>
                <h2>{changes.summary}</h2>
                {changes.files.length === 0 && <div className="empty">Builder proposed no file changes.</div>}
                {changes.files.map((file) => (
                  <details className="fileChange" key={file.path}>
                    <summary><b>{file.action}</b> {file.path}</summary>
                    {file.reason && <p>{file.reason}</p>}
                    <pre>{file.content}</pre>
                  </details>
                ))}
                {changes.files.length > 0 && (
                  <button className="approveButton" type="button" disabled={busy} onClick={applyChanges}>
                    Approve & apply {changes.files.length} file{changes.files.length === 1 ? "" : "s"}
                  </button>
                )}

                {changes.recommended_checks.length > 0 && (
                  <div className="checks">
                    <div className="sectionLabel">Recommended checks</div>
                    {changes.recommended_checks.map((check, index) => (
                      <button className="secondaryButton" type="button" key={`${check.kind}-${index}`} disabled={busy} onClick={() => runCheck(check)}>
                        Run {check.kind} · {check.cwd}
                      </button>
                    ))}
                  </div>
                )}

                {changes.notes?.length > 0 && <div className="notes">{changes.notes.join(" · ")}</div>}
              </div>
            )}
          </div>
        </section>
      </div>

      <section className="panel activityPanel">
        <div className="panelTitle">
          <div><span>03</span> Activity</div>
          <small>tool results</small>
        </div>
        <div className="activityList">
          {activity.length === 0 && <div className="empty">No tools have run yet.</div>}
          {activity.map((item, index) => (
            <article className={`activityItem ${item.ok ? "ok" : "bad"}`} key={index}>
              <b>{item.label}</b>
              <pre>{item.detail}</pre>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
