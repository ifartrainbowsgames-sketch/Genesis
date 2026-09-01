"use client";

import { FormEvent, useState } from "react";

import { api } from "../../lib/api";
import styles from "./research.module.css";

type Provider = "ollama" | "openai" | "anthropic";
type ResearchSource = {
  id: string;
  title: string;
  url: string;
  snippet: string;
  engine?: string | null;
  score?: number | null;
};
type ResearchReport = {
  query: string;
  answer: string;
  sources: ResearchSource[];
  provider: Provider;
  model: string;
  notes: string[];
};
type ResearchRun = { task_id: string; report: ResearchReport };

export default function ResearchPage() {
  const [provider, setProvider] = useState<Provider>("ollama");
  const [model, setModel] = useState("");
  const [query, setQuery] = useState("");
  const [maxResults, setMaxResults] = useState(8);
  const [language, setLanguage] = useState("all");
  const [timeRange, setTimeRange] = useState("");
  const [result, setResult] = useState<ResearchRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function runResearch(event: FormEvent) {
    event.preventDefault();
    const text = query.trim();
    if (!text || busy) return;
    setBusy(true);
    setError("");
    try {
      const response = await api<ResearchRun>("/v1/research", {
        method: "POST",
        body: JSON.stringify({
          query: text,
          provider,
          model: model.trim() || null,
          max_results: maxResults,
          language: language.trim() || "all",
          time_range: timeRange || null,
          safesearch: 1,
        }),
      });
      setResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <div className="eyebrow">GENESIS / SOURCE-TRACKED RESEARCH</div>
          <h1>Researcher</h1>
        </div>
        <div className="status"><span />{busy ? "working" : "ready"}</div>
      </header>

      {error && <div className="error">{error}</div>}

      <div className={styles.grid}>
        <section className={`panel ${styles.controls}`}>
          <div className="panelTitle"><div><span>01</span> Query</div><small>SearXNG → model synthesis</small></div>
          <form className={styles.form} onSubmit={runResearch}>
            <label>
              Research question
              <textarea rows={8} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="What do you want Genesis to investigate?" />
            </label>
            <div className={styles.twoCol}>
              <label>
                Provider
                <select value={provider} onChange={(event) => setProvider(event.target.value as Provider)}>
                  <option value="ollama">Ollama · local</option>
                  <option value="openai">OpenAI · optional cloud</option>
                  <option value="anthropic">Anthropic · optional cloud</option>
                </select>
              </label>
              <label>
                Model override
                <input value={model} onChange={(event) => setModel(event.target.value)} placeholder="default model" />
              </label>
            </div>
            <div className={styles.threeCol}>
              <label>
                Sources
                <input type="number" min={1} max={12} value={maxResults} onChange={(event) => setMaxResults(Number(event.target.value) || 1)} />
              </label>
              <label>
                Language
                <input value={language} onChange={(event) => setLanguage(event.target.value)} placeholder="all / en / de" />
              </label>
              <label>
                Time range
                <select value={timeRange} onChange={(event) => setTimeRange(event.target.value)}>
                  <option value="">any time</option>
                  <option value="day">day</option>
                  <option value="month">month</option>
                  <option value="year">year</option>
                </select>
              </label>
            </div>
            <button className="approveButton" disabled={busy || !query.trim()}>{busy ? "Researching…" : "Run research"}</button>
            <p className={styles.muted}>Genesis asks only the configured SearXNG broker for search results. The model receives result titles, URLs and snippets; it does not silently browse arbitrary pages.</p>
          </form>
        </section>

        <section className={`panel ${styles.answer}`}>
          <div className="panelTitle"><div><span>02</span> Synthesis</div><small>{result ? `${result.report.provider} · ${result.report.model}` : "waiting"}</small></div>
          {!result && <div className={styles.empty}>The source-grounded synthesis will appear here with inline source IDs such as [S1].</div>}
          {result && (
            <div className={styles.answerBody}>
              <div className={styles.meta}>task {result.task_id}</div>
              <h2>{result.report.query}</h2>
              <p className={styles.text}>{result.report.answer}</p>
              {result.report.notes.length > 0 && (
                <div className={styles.notes}>
                  {result.report.notes.map((note, index) => <p key={index}>{note}</p>)}
                </div>
              )}
            </div>
          )}
        </section>
      </div>

      <section className={`panel ${styles.sourcesPanel}`}>
        <div className="panelTitle"><div><span>03</span> Sources</div><small>{result ? `${result.report.sources.length} source(s)` : "source ledger"}</small></div>
        <div className={styles.sourceGrid}>
          {!result && <div className={styles.empty}>Search-result sources will be preserved here so you can inspect exactly what the Researcher used.</div>}
          {result?.report.sources.map((source) => (
            <article className={styles.sourceCard} key={source.id}>
              <div className={styles.sourceHead}><b>[{source.id}]</b><span>{source.engine || "search"}</span></div>
              <h3><a href={source.url} target="_blank" rel="noreferrer">{source.title}</a></h3>
              <p>{source.snippet || "No snippet returned."}</p>
              <code>{source.url}</code>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
