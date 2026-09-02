"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "../../lib/api";
import styles from "../control.module.css";

type Episodic = { id: string; conversation_id: string; role: string; content: string; created_at?: string };
type Knowledge = { id: string; kind: string; scope: string; scope_id?: string | null; title: string; content: string; confidence: number; source_ids: string[] };
type Consolidated = { conversation_id: string; records_read: number; knowledge_written: number; knowledge: Knowledge[] };

export default function MemoryPage() {
  const [conversationId, setConversationId] = useState("default");
  const [query, setQuery] = useState("");
  const [episodic, setEpisodic] = useState<Episodic[]>([]);
  const [knowledge, setKnowledge] = useState<Knowledge[]>([]);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    setError("");
    try {
      const [episodes, learned] = await Promise.all([
        api<Episodic[]>(`/v1/memory?conversation_id=${encodeURIComponent(conversationId)}&limit=50`),
        api<Knowledge[]>(`/v1/memory/knowledge?scope_id=${encodeURIComponent(conversationId)}&limit=50`),
      ]);
      setEpisodic(episodes);
      setKnowledge(learned);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [conversationId]);

  useEffect(() => { void refresh(); }, [refresh]);

  async function consolidate() {
    setBusy(true); setError("");
    try {
      const result = await api<Consolidated>("/v1/memory/consolidate", {
        method: "POST",
        body: JSON.stringify({ conversation_id: conversationId, max_records: 200 }),
      });
      setStatus(`Read ${result.records_read} episodic records and wrote ${result.knowledge_written} cognitive memory item(s).`);
      await refresh();
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  }

  async function search() {
    if (!query.trim()) return refresh();
    setBusy(true); setError("");
    try {
      const [episodes, learned] = await Promise.all([
        api<Episodic[]>("/v1/memory/search", { method: "POST", body: JSON.stringify({ query, conversation_id: conversationId, limit: 20 }) }),
        api<Knowledge[]>("/v1/memory/knowledge/search", { method: "POST", body: JSON.stringify({ query, conversation_id: conversationId, limit: 20 }) }),
      ]);
      setEpisodic(episodes); setKnowledge(learned);
      setStatus(`Search results for “${query}”.`);
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  }

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <h1>Memory</h1>
        <p>Episodic chat history stays intact. Consolidation creates source-linked semantic summaries and procedural preferences without erasing the original records.</p>
      </header>
      <section className={styles.grid}>
        <div className={`${styles.card} ${styles.full}`}>
          <div className={styles.row}>
            <input className={styles.input} value={conversationId} onChange={(e) => setConversationId(e.target.value)} placeholder="conversation id" />
            <input className={styles.input} value={query} onChange={(e) => setQuery(e.target.value)} placeholder="search memory" />
            <button className={styles.button} onClick={() => void search()} disabled={busy}>Search</button>
            <button className={styles.button} onClick={() => void consolidate()} disabled={busy}>Consolidate</button>
            <button className={styles.button} onClick={() => void refresh()} disabled={busy}>Refresh</button>
          </div>
          {status ? <div className={styles.meta}>{status}</div> : null}
          {error ? <div className={styles.error}>{error}</div> : null}
        </div>

        <div className={styles.card}>
          <h2>Episodic memory · {episodic.length}</h2>
          <div className={styles.list}>
            {episodic.map((item) => (
              <div className={styles.item} key={item.id}>
                <strong>{item.role} · {item.conversation_id}</strong>
                <div className={styles.meta}>{item.created_at ? new Date(item.created_at).toLocaleString() : ""}</div>
                <div className={styles.pre}>{item.content}</div>
              </div>
            ))}
          </div>
        </div>

        <div className={styles.card}>
          <h2>Cognitive memory · {knowledge.length}</h2>
          <div className={styles.list}>
            {knowledge.map((item) => (
              <div className={styles.item} key={item.id}>
                <strong>{item.title}</strong>
                <div className={styles.meta}>{item.kind} · {item.scope}:{item.scope_id ?? "global"} · confidence {item.confidence.toFixed(2)} · {item.source_ids.length} source(s)</div>
                <div className={styles.pre}>{item.content}</div>
              </div>
            ))}
          </div>
        </div>
      </section>
    </main>
  );
}
