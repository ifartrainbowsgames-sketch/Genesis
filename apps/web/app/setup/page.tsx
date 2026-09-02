"use client";

import { useEffect, useMemo, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import styles from "./setup.module.css";

type Provider = "ollama" | "openai" | "anthropic";
type SetupStatus = {
  complete: boolean;
  installerMode: boolean;
  provider: Provider;
  model: string;
  ollamaInstalled: boolean;
  ollamaRunning: boolean;
  embeddingModel: string;
};

const LOCAL_MODELS = [
  { id: "qwen3:8b", name: "Qwen 3 8B", note: "Balanced starter · lower hardware load" },
  { id: "qwen3-coder", name: "Qwen 3 Coder", note: "Coding-focused · recommended for Workbench" },
  { id: "gpt-oss:20b", name: "GPT-OSS 20B", note: "Stronger local model · needs more RAM/VRAM" },
  { id: "glm-4.7-flash", name: "GLM 4.7 Flash", note: "Fast coding model · best on stronger GPUs" },
];

const CLOUD_MODELS: Record<Exclude<Provider, "ollama">, Array<{ id: string; name: string }>> = {
  openai: [
    { id: "gpt-5.6-terra", name: "GPT-5.6 Terra · balanced" },
    { id: "gpt-5.6-sol", name: "GPT-5.6 Sol · strongest" },
    { id: "gpt-5.6-luna", name: "GPT-5.6 Luna · lower cost" },
  ],
  anthropic: [
    { id: "claude-sonnet-5", name: "Claude Sonnet 5" },
  ],
};

function message(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

export default function SetupPage() {
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [provider, setProvider] = useState<Provider>("ollama");
  const [model, setModel] = useState("qwen3:8b");
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [progress, setProgress] = useState<string[]>([]);

  const cloudModels = useMemo(() => provider === "ollama" ? [] : CLOUD_MODELS[provider], [provider]);

  function log(line: string) {
    setProgress((items) => [...items, line]);
  }

  async function refresh() {
    try {
      const next = await invoke<SetupStatus>("setup_status");
      setStatus(next);
      setProvider(next.provider);
      setModel(next.model || "qwen3:8b");
      if (next.complete) setReady(true);
    } catch (err) {
      setError(`Genesis Setup must run inside the Windows desktop installer. ${message(err)}`);
    }
  }

  useEffect(() => { void refresh(); }, []);

  function chooseProvider(next: Provider) {
    setProvider(next);
    setReady(false);
    setError("");
    if (next === "ollama") setModel("qwen3:8b");
    if (next === "openai") setModel("gpt-5.6-terra");
    if (next === "anthropic") setModel("claude-sonnet-5");
  }

  async function prepareLocal() {
    setBusy(true); setError(""); setReady(false); setProgress([]);
    try {
      let current = await invoke<SetupStatus>("setup_status");
      if (!current.ollamaInstalled) {
        log("Installing Ollama through Windows Package Manager…");
        log(await invoke<string>("setup_install_ollama"));
      } else {
        log("Ollama installation detected.");
      }

      current = await invoke<SetupStatus>("setup_status");
      if (!current.ollamaRunning) {
        log("Starting the local Ollama service…");
        log(await invoke<string>("setup_start_ollama"));
      } else {
        log("Ollama service is already running.");
      }

      log(`Pulling ${model}. This can take several minutes on the first install…`);
      log(await invoke<string>("setup_pull_model", { model }));
      await invoke("setup_save", { provider: "ollama", model });
      log("Local AI setup verified. Genesis is ready.");
      setReady(true);
      await refresh();
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }

  async function prepareCloud() {
    if (provider === "ollama") return;
    setBusy(true); setError(""); setReady(false); setProgress([]);
    try {
      log(`Validating the ${provider === "openai" ? "OpenAI" : "Anthropic"} API key…`);
      log(await invoke<string>("setup_validate_cloud", { provider, apiKey }));
      await invoke("setup_save", { provider, model });
      log("Cloud AI setup verified. Genesis is ready.");
      setApiKey("");
      setReady(true);
      await refresh();
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }

  async function finish() {
    setBusy(true); setError("");
    try {
      await invoke("setup_finish");
    } catch (err) {
      setError(message(err));
      setBusy(false);
    }
  }

  return (
    <main className={styles.overlay}>
      <div className={styles.shell}>
        <section className={styles.card}>
          <header className={styles.header}>
            <div>
              <div className={styles.kicker}>Genesis 0.10 · One-click setup</div>
              <h1>Choose the brain for your Workbench.</h1>
              <p>Genesis verifies your AI provider before the installer finishes. Local mode installs and starts Ollama for you. Cloud mode validates your API key and keeps it in the Windows credential vault.</p>
            </div>
            <div className={styles.step}>{status?.installerMode ? "Installer setup" : "First-run setup"}</div>
          </header>

          <div className={styles.body}>
            <div className={styles.choiceGrid}>
              <button className={`${styles.choice} ${provider === "ollama" ? styles.choiceActive : ""}`} onClick={() => chooseProvider("ollama")} disabled={busy}>
                <strong>Local with Ollama</strong>
                <span>Private local models. Genesis detects Ollama, installs it if needed, starts it, then downloads the models you select.</span>
                <span className={styles.recommended}>Recommended starting point</span>
              </button>
              <button className={`${styles.choice} ${provider !== "ollama" ? styles.choiceActive : ""}`} onClick={() => chooseProvider("openai")} disabled={busy}>
                <strong>Cloud API</strong>
                <span>Use OpenAI or Anthropic without downloading a large local chat model. Your key is validated before setup completes.</span>
              </button>
            </div>

            {provider === "ollama" ? (
              <div className={styles.section}>
                <div className={styles.sectionTitle}>
                  <strong>1. Ollama + model</strong>
                  <span className={`${styles.status} ${status?.ollamaInstalled && status?.ollamaRunning ? styles.good : styles.warn}`}>
                    {status?.ollamaInstalled ? (status.ollamaRunning ? "Ollama ready" : "Ollama installed · service stopped") : "Ollama not installed"}
                  </span>
                </div>
                <div className={styles.models}>
                  {LOCAL_MODELS.map((item) => (
                    <button key={item.id} className={`${styles.model} ${model === item.id ? styles.modelActive : ""}`} onClick={() => { setModel(item.id); setReady(false); }} disabled={busy}>
                      <strong>{item.name}</strong>
                      <small>{item.note}</small>
                    </button>
                  ))}
                </div>
                <p className={styles.note}>Genesis also installs the {status?.embeddingModel ?? "nomic-embed-text"} embedding model for memory. Model download time depends on your connection and hardware.</p>
              </div>
            ) : (
              <div className={styles.section}>
                <div className={styles.sectionTitle}><strong>1. Cloud provider</strong><span className={styles.status}>API validation required</span></div>
                <div className={styles.row}>
                  <select className={styles.select} value={provider} onChange={(event) => chooseProvider(event.target.value as Provider)} disabled={busy}>
                    <option value="openai">OpenAI</option>
                    <option value="anthropic">Anthropic</option>
                  </select>
                  <select className={styles.select} value={model} onChange={(event) => { setModel(event.target.value); setReady(false); }} disabled={busy}>
                    {cloudModels.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                  </select>
                </div>
                <div className={styles.row} style={{ marginTop: 10 }}>
                  <input className={styles.input} type="password" autoComplete="off" spellCheck={false} value={apiKey} onChange={(event) => { setApiKey(event.target.value); setReady(false); }} placeholder={provider === "openai" ? "OpenAI API key" : "Anthropic API key"} />
                </div>
                <p className={styles.note}>The key is not written to setup.json. Genesis stores it through the operating-system credential store and only injects it into the local sidecar process.</p>
              </div>
            )}

            {progress.length ? <div className={styles.progress}>{progress.join("\n")}</div> : null}
            {error ? <div className={styles.error}>{error}</div> : null}
            {ready ? <div className={styles.ready}>Setup checks are green. Workbench can start.</div> : null}

            <div className={styles.actions}>
              <span className={styles.note}>No workspace mutation or external worker is enabled by this step. Those still use Genesis approval gates.</span>
              <div className={styles.row}>
                <button className={styles.button} onClick={() => void refresh()} disabled={busy}>Check again</button>
                {!ready ? (
                  <button className={styles.primary} onClick={() => void (provider === "ollama" ? prepareLocal() : prepareCloud())} disabled={busy || (provider !== "ollama" && apiKey.trim().length < 12)}>
                    {busy ? "Preparing…" : provider === "ollama" ? "Install & prepare local AI" : "Validate & use cloud AI"}
                  </button>
                ) : (
                  <button className={styles.primary} onClick={() => void finish()} disabled={busy}>
                    {status?.installerMode ? "Finish installation" : "Open Workbench"}
                  </button>
                )}
              </div>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
