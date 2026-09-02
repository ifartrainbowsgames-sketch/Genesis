"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "../../lib/api";
import styles from "../product-pages.module.css";

type Workspace = { name: string; path: string; is_git: boolean; selected: boolean };
type WorkspaceList = { current: Workspace; candidates: Workspace[] };

type GitRead = { tool: string; result: Record<string, unknown> };

export default function ProjectsPage() {
  const [workspaces, setWorkspaces] = useState<WorkspaceList | null>(null);
  const [gitStatus, setGitStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    setError("");
    try {
      const result = await api<WorkspaceList>("/v1/workspaces");
      setWorkspaces(result);
      try {
        const status = await api<GitRead>("/v1/tools/read", {
          method: "POST",
          body: JSON.stringify({ tool: "git.status", arguments: {} }),
        });
        setGitStatus(String(status.result.output ?? ""));
      } catch {
        setGitStatus("");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  async function selectWorkspace(path: string) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await api<Workspace>("/v1/workspaces/select", {
        method: "POST",
        body: JSON.stringify({ path }),
      });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1>Projects</h1>
          <p>Choose what Genesis is allowed to understand and work on. Project discovery stays inside the roots approved during setup.</p>
        </div>
        <div className={styles.actions}>
          <button className={styles.button} type="button" disabled={busy} onClick={() => void refresh()}>Refresh</button>
        </div>
      </header>

      {error ? <div className={styles.error} role="alert">{error}</div> : null}

      {workspaces ? (
        <>
          <section className={styles.card}>
            <div className={styles.cardHeader}><strong>Current project</strong><span>{workspaces.current.is_git ? "Git repository" : "Folder"}</span></div>
            <div className={styles.row}>
              <div><span className={styles.rowTitle}>{workspaces.current.name}</span><span className={styles.rowDetail}>{workspaces.current.path}</span></div>
              <span className={`${styles.badge} ${styles.selected}`}>active</span>
            </div>
            {gitStatus ? <div className={styles.row}><div><span className={styles.rowTitle}>Git</span><span className={styles.rowDetail}>{gitStatus.split("\n").slice(0, 3).join(" · ")}</span></div></div> : null}
          </section>

          <section className={styles.card}>
            <div className={styles.cardHeader}><strong>Available projects</strong><span>{workspaces.candidates.length}</span></div>
            {workspaces.candidates.map((item) => (
              <button key={item.path} className={styles.row} type="button" disabled={busy || item.selected} onClick={() => void selectWorkspace(item.path)}>
                <div><span className={styles.rowTitle}>{item.name}</span><span className={styles.rowDetail}>{item.path}</span></div>
                <span className={`${styles.badge} ${item.selected ? styles.selected : ""}`}>{item.selected ? "active" : item.is_git ? "git" : "folder"}</span>
              </button>
            ))}
          </section>
        </>
      ) : <div className={styles.empty}>Loading projects…</div>}
    </main>
  );
}
