"use client";

import { useEffect, useState } from "react";

import { api } from "../../lib/api";
import styles from "./diagnostics.module.css";

type ComponentHealth = {
  status: string;
  detail: string;
  models?: number;
  servers?: number;
};
type Health = {
  status: string;
  components: Record<string, ComponentHealth>;
};

const LABELS: Record<string, string> = {
  database: "PostgreSQL / pgvector",
  ollama: "Ollama",
  research: "SearXNG research",
  voice: "whisper.cpp voice",
  github: "GitHub",
  mcp: "MCP registry",
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

  useEffect(() => {
    void refresh();
  }, []);

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <div className="eyebrow">GENESIS / LOCAL DEPENDENCIES</div>
          <h1>Diagnostics</h1>
        </div>
        <div className="status"><span />{busy ? "checking" : health?.status ?? "loading"}</div>
      </header>

      {error && <div className="error">{error}</div>}

      <section className={`panel ${styles.summary}`}>
        <div>
          <h2>{health ? `System ${health.status}` : "Checking local services…"}</h2>
          <p>Diagnostics do not expose API keys or secret values.</p>
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

      <section className={`panel ${styles.note}`}>
        PostgreSQL and Ollama are treated as the core local services. Research, voice, GitHub, and MCP can remain intentionally unconfigured. Use this screen before a desktop build to see which capabilities will be available at runtime.
      </section>
    </main>
  );
}
