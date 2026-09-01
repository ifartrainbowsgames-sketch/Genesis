"use client";

import { useEffect, useState } from "react";

import { api } from "../../lib/api";
import styles from "./diagnostics.module.css";

type ComponentHealth = {
  status: string;
  detail: string;
  models?: number;
  servers?: number;
  workers?: number;
  external?: number;
  running?: boolean;
  enabled?: boolean;
};
type Health = {
  status: string;
  components: Record<string, ComponentHealth>;
  recommendations?: string[];
};

const LABELS: Record<string, string> = {
  database: "PostgreSQL / pgvector",
  ollama: "Ollama",
  research: "SearXNG research",
  voice: "whisper.cpp voice",
  github: "GitHub",
  mcp: "MCP registry",
  workers: "Worker registry",
  scheduler: "Durable scheduler",
  cognitive_memory: "Cognitive memory",
  evolution: "Shadow evolution",
};

export default function DiagnosticsPage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function refresh() {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      setHealth(await api<Health>("/v1/system/health"));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => { void refresh(); }, []);

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <div className="eyebrow">GENESIS / DOCTOR</div>
          <h1>Diagnostics</h1>
        </div>
        <div className="status"><span />{busy ? "checking" : health?.status ?? "loading"}</div>
      </header>

      {error && <div className="error">{error}</div>}

      <section className={`panel ${styles.summary}`}>
        <div>
          <h2>{health ? `System ${health.status}` : "Checking local services…"}</h2>
          <p>Diagnostics report capabilities and recovery hints without exposing API keys or secret values.</p>
        </div>
        <button disabled={busy} onClick={refresh}>{busy ? "Checking…" : "Refresh"}</button>
      </section>

      <div className={styles.grid}>
        {health && Object.entries(health.components).map(([name, component]) => (
          <article className={styles.card} key={name}>
            <div className={styles.head}>
              <h3>{LABELS[name] ?? name}</h3>
              <span className={`${styles.badge} ${styles[component.status] ?? ""}`}>{component.status.replaceAll("_", " ")}</span>
            </div>
            <p>{component.detail}</p>
          </article>
        ))}
      </div>

      {health?.recommendations?.length ? (
        <section className={`panel ${styles.note}`}>
          <strong>Recovery hints</strong>
          <ul>{health.recommendations.map((item) => <li key={item}>{item}</li>)}</ul>
          <p>For local prerequisite checks on Windows, run <code>./scripts/doctor.ps1</code> from the repository root.</p>
        </section>
      ) : null}

      <section className={`panel ${styles.note}`}>
        PostgreSQL and Ollama are the core local services. Research, voice, GitHub, MCP, and external workers can remain intentionally unconfigured. The scheduler, cognitive memory, and evolution layers are local runtime capabilities; evolved prompts remain shadow-only until a human promotion gate succeeds.
      </section>
    </main>
  );
}
