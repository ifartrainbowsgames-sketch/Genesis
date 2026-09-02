"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../../lib/api";
import styles from "../control.module.css";

type Task = { id: string; title: string; status: string; provider: string; model?: string | null; stop_reason?: string | null; created_at?: string };
type Event = { id: string; sequence: number; event_type: string; payload: unknown; created_at?: string };
type Artifact = { id: string; kind: string; payload: unknown; created_at?: string };
type TaskDetail = { task: Task; artifacts: Artifact[]; events: Event[] };
type Worker = { name: string; type: "builtin" | "command" | "http"; detail: string };
type WorkerResult = { worker: string; output: string; task_id?: string | null; metadata: Record<string, unknown> };
type Schedule = { id: string; name: string; enabled: boolean; interval_seconds: number; next_run_at: string; last_run_at?: string | null; last_task_id?: string | null; last_error?: string | null; request: { task: string; provider: string } };
type Proposal = { approval_id: string; expires_in_seconds: number };
type Execution = { tool: string; result: Record<string, unknown> };

async function approvedExternalWorker(worker: string, prompt: string) {
  const proposal = await api<Proposal>("/v1/tools/propose", {
    method: "POST",
    body: JSON.stringify({ tool: "worker.run", arguments: { worker, prompt } }),
  });
  if (!window.confirm(`Approve external worker “${worker}”?\n\nThis executes an explicitly allowlisted worker. Approval expires in ${proposal.expires_in_seconds}s.`)) {
    throw new Error("External worker approval cancelled");
  }
  return api<Execution>("/v1/tools/execute", {
    method: "POST",
    body: JSON.stringify({ approval_id: proposal.approval_id, approved: true }),
  });
}

export default function RuntimePage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [workers, setWorkers] = useState<Worker[]>([]);
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState("");
  const [detail, setDetail] = useState<TaskDetail | null>(null);
  const [worker, setWorker] = useState("genesis-team");
  const [prompt, setPrompt] = useState("Inspect the selected workspace and propose the highest-value improvement without applying mutations.");
  const [workerOutput, setWorkerOutput] = useState("");
  const [scheduleName, setScheduleName] = useState("Daily Genesis review");
  const [scheduleTask, setScheduleTask] = useState("Review the workspace for regressions and propose improvements. Do not apply changes automatically.");
  const [interval, setInterval] = useState(86400);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const selectedWorker = useMemo(() => workers.find((item) => item.name === worker), [workers, worker]);

  const refresh = useCallback(async () => {
    setError("");
    try {
      const [taskRows, workerRows, scheduleRows] = await Promise.all([
        api<Task[]>("/v1/tasks?limit=50"),
        api<Worker[]>("/v1/workers"),
        api<Schedule[]>("/v1/schedules"),
      ]);
      setTasks(taskRows); setWorkers(workerRows); setSchedules(scheduleRows);
      if (!workerRows.some((item) => item.name === worker) && workerRows.length) setWorker(workerRows[0].name);
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
  }, [worker]);

  useEffect(() => { void refresh(); }, [refresh]);

  async function loadTask(taskId: string) {
    setSelectedTaskId(taskId); setError("");
    try { setDetail(await api<TaskDetail>(`/v1/tasks/${taskId}`)); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); }
  }

  async function retryTask() {
    if (!selectedTaskId || !window.confirm("Retry this task from its immutable team_request artifact?")) return;
    setBusy(true); setError("");
    try {
      const result = await api<{ task_id: string; status: string }>(`/v1/tasks/${selectedTaskId}/retry`, { method: "POST" });
      await refresh(); await loadTask(result.task_id);
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  }

  async function runSelectedWorker() {
    if (!prompt.trim()) return;
    setBusy(true); setError(""); setWorkerOutput("");
    try {
      if (selectedWorker?.type === "builtin") {
        const result = await api<WorkerResult>("/v1/workers/run", {
          method: "POST",
          body: JSON.stringify({ worker, prompt, provider: "ollama", use_research: false, context: {} }),
        });
        setWorkerOutput(result.output);
      } else {
        const result = await approvedExternalWorker(worker, prompt);
        setWorkerOutput(JSON.stringify(result.result, null, 2));
      }
      await refresh();
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  }

  async function createSchedule() {
    if (!window.confirm(`Create durable schedule “${scheduleName}” every ${interval} seconds?`)) return;
    setBusy(true); setError("");
    try {
      await api<Schedule>("/v1/schedules", {
        method: "POST",
        body: JSON.stringify({
          name: scheduleName,
          interval_seconds: interval,
          run_immediately: false,
          request: { task: scheduleTask, provider: "ollama", max_agent_calls: 4, use_research: false, research_max_results: 8 },
        }),
      });
      await refresh();
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  }

  async function toggleSchedule(item: Schedule) {
    setBusy(true); setError("");
    try {
      await api<Schedule>(`/v1/schedules/${item.id}/toggle`, { method: "POST", body: JSON.stringify({ enabled: !item.enabled }) });
      await refresh();
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  }

  async function removeSchedule(item: Schedule) {
    if (!window.confirm(`Delete schedule “${item.name}”?`)) return;
    setBusy(true); setError("");
    try { await api(`/v1/schedules/${item.id}`, { method: "DELETE" }); await refresh(); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  }

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <h1>Runtime</h1>
        <p>Durable task history, replay lineage, bounded schedules, and one worker registry. External workers are approval-gated; schedules run the bounded Genesis team and never apply workspace mutations automatically.</p>
      </header>
      <section className={styles.grid}>
        <div className={styles.card}>
          <h2>Workers</h2>
          <div className={styles.row}>
            <select className={styles.select} value={worker} onChange={(e) => setWorker(e.target.value)}>
              {workers.map((item) => <option key={item.name} value={item.name}>{item.name} · {item.type}</option>)}
            </select>
            <button className={styles.button} disabled={busy} onClick={() => void runSelectedWorker()}>Run {selectedWorker?.type === "builtin" ? "bounded" : "approved"}</button>
          </div>
          <textarea className={styles.textarea} value={prompt} onChange={(e) => setPrompt(e.target.value)} />
          {selectedWorker ? <div className={styles.meta}>{selectedWorker.detail}</div> : null}
          {workerOutput ? <pre className={styles.pre}>{workerOutput}</pre> : null}
        </div>

        <div className={styles.card}>
          <h2>Durable schedule</h2>
          <div className={styles.row}><input className={styles.input} value={scheduleName} onChange={(e) => setScheduleName(e.target.value)} /></div>
          <textarea className={styles.textarea} value={scheduleTask} onChange={(e) => setScheduleTask(e.target.value)} />
          <div className={styles.row}>
            <input className={styles.input} type="number" min={60} value={interval} onChange={(e) => setInterval(Number(e.target.value))} />
            <button className={styles.button} disabled={busy || interval < 60} onClick={() => void createSchedule()}>Create schedule</button>
          </div>
          <div className={styles.list}>
            {schedules.map((item) => (
              <div className={styles.item} key={item.id}>
                <strong>{item.name}</strong>
                <div className={styles.meta}>{item.enabled ? "enabled" : "disabled"} · every {item.interval_seconds}s · next {new Date(item.next_run_at).toLocaleString()}</div>
                <div className={styles.meta}>{item.request.task}</div>
                {item.last_error ? <div className={styles.error}>{item.last_error}</div> : null}
                <div className={styles.row}>
                  <button className={styles.button} disabled={busy} onClick={() => void toggleSchedule(item)}>{item.enabled ? "Disable" : "Enable"}</button>
                  <button className={styles.button} disabled={busy} onClick={() => void removeSchedule(item)}>Delete</button>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className={styles.card}>
          <h2>Tasks · {tasks.length}</h2>
          <div className={styles.list}>
            {tasks.map((task) => (
              <button className={`${styles.item} ${styles.button}`} style={{ textAlign: "left" }} key={task.id} onClick={() => void loadTask(task.id)}>
                <strong>{task.title}</strong>
                <span className={styles.meta}>{task.status} · {task.provider}{task.stop_reason ? ` · ${task.stop_reason}` : ""}</span>
              </button>
            ))}
          </div>
        </div>

        <div className={styles.card}>
          <h2>Task replay / event log</h2>
          {detail ? (
            <>
              <div className={styles.row}><button className={styles.button} disabled={busy} onClick={() => void retryTask()}>Retry from artifact</button></div>
              <div className={styles.item}><strong>{detail.task.title}</strong><div className={styles.meta}>{detail.task.status}</div></div>
              <h2>Events</h2>
              <div className={styles.list}>{detail.events.map((event) => <div className={styles.item} key={event.id}><strong>#{event.sequence} {event.event_type}</strong><pre className={styles.pre}>{JSON.stringify(event.payload, null, 2)}</pre></div>)}</div>
              <h2>Artifacts</h2>
              <div className={styles.list}>{detail.artifacts.map((artifact) => <div className={styles.item} key={artifact.id}><strong>{artifact.kind}</strong><pre className={styles.pre}>{JSON.stringify(artifact.payload, null, 2)}</pre></div>)}</div>
            </>
          ) : <div className={styles.meta}>Select a task to inspect its immutable artifacts and ordered event history.</div>}
        </div>
        {error ? <div className={`${styles.card} ${styles.full} ${styles.error}`}>{error}</div> : null}
      </section>
    </main>
  );
}
