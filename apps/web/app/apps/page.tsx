"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "../../lib/api";
import styles from "../control.module.css";

type CatalogManifest = {
  app_id: string;
  name: string;
  category: string;
  version: string;
  platform: string[];
  install_type: "winget" | "ollama_pull";
  license_tier: "bundle" | "auto_install" | "handoff" | "avoid";
  license_note: string;
  launch_command: string[] | null;
  published_at: string;
};

type CatalogEntry = {
  manifest: CatalogManifest;
  manifest_hash: string;
  installed: boolean;
  installed_version?: string | null;
  status?: string | null;
};

type Proposal = { approval_id: string; expires_in_seconds: number };
type Execution = { tool: string; result: Record<string, unknown> };

async function approvedCatalogAction(tool: string, args: Record<string, unknown>, confirmMessage: string) {
  const proposal = await api<Proposal>("/v1/tools/propose", {
    method: "POST",
    body: JSON.stringify({ tool, arguments: args }),
  });
  if (!window.confirm(`${confirmMessage}\n\nApproval expires in ${proposal.expires_in_seconds}s.`)) {
    throw new Error("Cancelled");
  }
  return api<Execution>("/v1/tools/execute", {
    method: "POST",
    body: JSON.stringify({ approval_id: proposal.approval_id, approved: true }),
  });
}

const CATEGORY_LABELS: Record<string, string> = {
  terminal: "Terminals",
  "local-llm": "Local LLMs",
};

export default function AppsPage() {
  const [entries, setEntries] = useState<CatalogEntry[]>([]);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState("");

  const refresh = useCallback(async () => {
    setError("");
    try {
      const data = await api<{ entries: CatalogEntry[] }>("/v1/catalog");
      setEntries(data.entries);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function install(entry: CatalogEntry) {
    setBusyId(entry.manifest.app_id);
    setError("");
    setLastResult("");
    try {
      const result = await approvedCatalogAction(
        "catalog.install",
        { app_id: entry.manifest.app_id, manifest_hash: entry.manifest_hash },
        `Install “${entry.manifest.name}” (${entry.manifest.install_type})?\n\n${entry.manifest.license_note}`,
      );
      setLastResult(JSON.stringify(result.result, null, 2));
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusyId(null);
    }
  }

  async function launch(entry: CatalogEntry) {
    setBusyId(entry.manifest.app_id);
    setError("");
    setLastResult("");
    try {
      const result = await approvedCatalogAction(
        "catalog.launch",
        { app_id: entry.manifest.app_id, manifest_hash: entry.manifest_hash },
        `Launch “${entry.manifest.name}”?`,
      );
      setLastResult(JSON.stringify(result.result, null, 2));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusyId(null);
    }
  }

  async function uninstall(entry: CatalogEntry) {
    setBusyId(entry.manifest.app_id);
    setError("");
    setLastResult("");
    try {
      const result = await approvedCatalogAction(
        "catalog.uninstall",
        { app_id: entry.manifest.app_id },
        `Uninstall “${entry.manifest.name}”?`,
      );
      setLastResult(JSON.stringify(result.result, null, 2));
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusyId(null);
    }
  }

  const categories = Array.from(new Set(entries.map((entry) => entry.manifest.category)));

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <h1>App catalog</h1>
        <p>
          One-click local install/launch for AI and dev tools. Entries are declarative manifests only (winget or
          Ollama&apos;s own pull), never arbitrary scripts. Every install/launch is approval-gated and scoped to the
          exact catalog entry version you approved.
        </p>
      </header>
      <section className={styles.grid}>
        {categories.map((category) => (
          <div className={styles.card} key={category}>
            <h2>{CATEGORY_LABELS[category] ?? category}</h2>
            <div className={styles.list}>
              {entries
                .filter((entry) => entry.manifest.category === category)
                .map((entry) => (
                  <div className={styles.item} key={entry.manifest.app_id}>
                    <strong>
                      {entry.manifest.name} · {entry.manifest.version}
                    </strong>
                    <div className={styles.meta}>
                      {entry.manifest.license_tier} · {entry.manifest.install_type}
                      {entry.installed ? ` · installed (${entry.installed_version})` : ""}
                    </div>
                    <div className={styles.meta}>{entry.manifest.license_note}</div>
                    <div className={styles.row}>
                      <button
                        className={styles.button}
                        disabled={busyId === entry.manifest.app_id}
                        onClick={() => void install(entry)}
                      >
                        {entry.installed ? "Reinstall" : "Install"}
                      </button>
                      {entry.manifest.launch_command ? (
                        <button
                          className={styles.button}
                          disabled={busyId === entry.manifest.app_id || !entry.installed}
                          onClick={() => void launch(entry)}
                        >
                          Launch
                        </button>
                      ) : null}
                      {entry.installed ? (
                        <button
                          className={styles.button}
                          disabled={busyId === entry.manifest.app_id}
                          onClick={() => void uninstall(entry)}
                        >
                          Uninstall
                        </button>
                      ) : null}
                    </div>
                  </div>
                ))}
            </div>
          </div>
        ))}
        {lastResult ? (
          <div className={`${styles.card} ${styles.full}`}>
            <h2>Last action result</h2>
            <pre className={styles.pre}>{lastResult}</pre>
          </div>
        ) : null}
        {error ? <div className={`${styles.card} ${styles.full} ${styles.error}`}>{error}</div> : null}
      </section>
    </main>
  );
}
