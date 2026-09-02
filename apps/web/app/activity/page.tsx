"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "../../lib/api";
import styles from "../product-pages.module.css";

type TaskSummary = {
  id: string;
  title: string;
  status: string;
  provider: string;
  model?: string | null;
  workspace: string;
  stop_reason?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};
type RunEvent = { id: string; sequence: number; event_type: string; payload: unknown; created_at?: string | null };
type Artifact = { id: string; kind: string; payload: unknown; created_at?: string | null };
type TaskDetail = { task: TaskSummary; events: RunEvent[]; artifacts: Artifact[] };

function relativeTime(value?: string | null) {
  if (!value) return "";
  const then = new Date(value).getTime();
  if (!Number.isFinite(then)) return "";
  const seconds = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  return `${hours}h ago`;
}

export default function ActivityPage() {
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [detail, setDetail] = useState<TaskDetail | null>(null);
  const [error, setError] = useState("");

  const refreshTasks = useCallback(async () => {
    try {
      const result = await api<TaskSummary[]>("/v1/tasks?limit=50");
      setTasks(result);
      setSelectedId((current) => current || result[0]?.id || "");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  const refreshDetail = useCallback(async (id: string) => {
    if (!id) return;
    try {
      setDetail(await api<TaskDetail>(`/v1/tasks/${encodeURIComponent(id)}`));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => { void refreshTasks(); }, [refreshTasks]);
  useEffect(() => { void refreshDetail(selectedId); }, [selectedId, refreshDetail]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void refreshTasks();
      if (selectedId) void refreshDetail(selectedId);
    }, 1500);
    return () => window.clearInterval(timer);
  }, [refreshTasks, refreshDetail, selectedId]);

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1>Activity</h1>
          <p>The durable record of what Genesis actually did: tasks, agent transitions, artifacts and stop reasons.</p>
        </div>
        <div className={styles.actions}>
          <button className={styles.button} type="button" onClick={() => { void refreshTasks(); if (selectedId) void refreshDetail(selectedId); }}>Refresh</button>
        </div>
      </header>

      {error ? <div className={styles.error} role="alert">{error}</div> : null}

      <div className={styles.detailGrid}>
        <section className={`${styles.card} ${styles.taskList}`}>
          <div className={styles.cardHeader}><strong>Tasks</strong><span>{tasks.length}</span></div>
          {tasks.length ? tasks.map((task) => (
            <button key={task.id} className={styles.row} type="button" onClick={() => setSelectedId(task.id)}>
              <div>
                <span className={styles.rowTitle}>{task.title}</span>
                <span className={styles.rowDetail}>{relativeTime(task.updated_at || task.created_at)}{task.stop_reason ? ` · ${task.stop_reason}` : ""}</span>
              </div>
              <span className={`${styles.badge} ${selectedId === task.id ? styles.selected : ""}`}>{task.status}</span>
            </button>
          )) : <div className={styles.empty}>No tasks yet. Ask Genesis to build, review or research something.</div>}
        </section>

        <section className={styles.card}>
          <div className={styles.cardHeader}>
            <strong>{detail?.task.title ?? "Task evidence"}</strong>
            <span>{detail ? `${detail.events.length} events · ${detail.artifacts.length} artifacts` : "select a task"}</span>
          </div>
          {detail ? (
            <div className={styles.eventList} aria-live="polite">
              {detail.events.map((event) => (
                <div className={styles.event} key={event.id}>
                  <strong>{String(event.sequence).padStart(2, "0")} · {event.event_type}</strong>
                  <pre>{JSON.stringify(event.payload, null, 2)}</pre>
                </div>
              ))}
              {detail.events.length === 0 ? <div className={styles.empty}>No runtime events recorded for this task.</div> : null}
            </div>
          ) : <div className={styles.empty}>Choose a task to inspect its execution record.</div>}
        </section>
      </div>
    </main>
  );
}
