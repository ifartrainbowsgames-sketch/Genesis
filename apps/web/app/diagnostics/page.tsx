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
  schemaVersion?: number | null;
  expectedSchemaVersion?: number;
};
type Health = {
  status: string;
  components: Record<string, ComponentHealth>;
  recommendations?: string[];
};
type BackupInfo = {
  name: string;
  bytes: number;
  schemaVersion: number;
  modifiedAt: string;
};
type BackupList = { backups: BackupInfo[] };
type RestoreStage = { staged: boolean; restartRequired: boolean; name: string; schemaVersion: number };

const LABELS: Record<string, string> = {
  database: "Durable database",
  ai_provider: "Selected AI provider",
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

function formatBytes(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function DiagnosticsPage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [desktop, setDesktop] = useState(false);
  const [backups, setBackups] = useState<BackupInfo[]>([]);
  const [storageBusy, setStorageBusy] = useState(false);
  const [storageMessage, setStorageMessage] = useState("");

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

  async function refreshBackups() {
    try {
      const result = await api<BackupList>("/v1/system/backups");
      setBackups(result.backups);
    } catch (err) {
      setStorageMessage(err instanceof Error ? err.message : String(err));
    }
  }

  async function createBackup() {
    if (storageBusy) return;
    setStorageBusy(true);
    setStorageMessage("");
    try {
      const created = await api<BackupInfo>("/v1/system/backups", { method: "POST" });
      setStorageMessage(`Backup created: ${created.name}`);
      await refreshBackups();
    } catch (err) {
      setStorageMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setStorageBusy(false);
    }
  }

  async function restoreBackup(backup: BackupInfo) {
    if (storageBusy) return;
    const confirmed = window.confirm(
      `Restore ${backup.name}? Genesis will restart. The current database will be saved automatically as a pre-restore safety backup.`,
    );
    if (!confirmed) return;

    setStorageBusy(true);
    setStorageMessage("Validating and staging restore…");
    try {
      const staged = await api<RestoreStage>(
        `/v1/system/backups/${encodeURIComponent(backup.name)}/restore`,
        { method: "POST" },
      );
      if (!staged.staged || !staged.restartRequired) throw new Error("Genesis did not stage the restore safely");
      setStorageMessage("Restore validated. Restarting Genesis…");
      const { invoke } = await import("@tauri-apps/api/core");
      await invoke("runtime_restart");
    } catch (err) {
      setStorageMessage(err instanceof Error ? err.message : String(err));
      setStorageBusy(false);
    }
  }

  useEffect(() => {
    const tauriWindow = window as Window & { __TAURI_INTERNALS__?: unknown };
    const isDesktop = Boolean(tauriWindow.__TAURI_INTERNALS__);
    setDesktop(isDesktop);
    void refresh();
    if (isDesktop) void refreshBackups();
  }, []);

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
            {name === "database" && component.expectedSchemaVersion ? (
              <p>Schema: {component.schemaVersion ?? "unknown"} / expected {component.expectedSchemaVersion}</p>
            ) : null}
          </article>
        ))}
      </div>

      {desktop ? (
        <section className={`panel ${styles.storage}`}>
          <div className={styles.storageHead}>
            <div>
              <strong>Desktop data recovery</strong>
              <p>Backups use SQLite&apos;s online backup API. Restore is staged and validated first; Genesis creates an automatic safety copy of the current DB before applying it on restart.</p>
            </div>
            <button disabled={storageBusy} onClick={() => void createBackup()}>{storageBusy ? "Working…" : "Create backup"}</button>
          </div>
          {storageMessage ? <div className={styles.storageMessage}>{storageMessage}</div> : null}
          <div className={styles.backupList}>
            {backups.length === 0 ? <p>No validated Genesis backups yet.</p> : backups.map((backup) => (
              <div className={styles.backupRow} key={backup.name}>
                <div>
                  <strong>{backup.name}</strong>
                  <small>{formatBytes(backup.bytes)} · schema {backup.schemaVersion} · {new Date(backup.modifiedAt).toLocaleString()}</small>
                </div>
                <button className={styles.restoreButton} disabled={storageBusy} onClick={() => void restoreBackup(backup)}>Restore</button>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {health?.recommendations?.length ? (
        <section className={`panel ${styles.note}`}>
          <strong>Recovery hints</strong>
          <ul>{health.recommendations.map((item) => <li key={item}>{item}</li>)}</ul>
          <p>For local prerequisite checks on Windows, run <code>./scripts/doctor.ps1</code> from the repository root.</p>
        </section>
      ) : null}

      <section className={`panel ${styles.note}`}>
        The selected AI provider and durable database are the only core readiness requirements. Research, voice, GitHub, MCP, and external workers can remain intentionally unconfigured. The scheduler, cognitive memory, and evolution layers are local runtime capabilities; evolved prompts remain shadow-only until a human promotion gate succeeds.
      </section>
    </main>
  );
}
