"use client";

import { useEffect, useMemo, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import styles from "./setup.module.css";

type Provider = "ollama" | "openai" | "anthropic";
type HardwareProfile = {
  totalMemoryGb: number;
  freeDiskGb: number;
  gpuName: string;
  recommendedModel: string;
};
type SetupStatus = {
  complete: boolean;
  installerMode: boolean;
  provider: Provider;
  model: string;
  workspace?: string | null;
  ollamaInstalled: boolean;
  ollamaRunning: boolean;
  embeddingModel: string;
  hardware: HardwareProfile;
};
type VerificationCheck = { name: string; status: "ready" | "failed"; detail: string };
type SetupVerification = { ready: boolean; checks: VerificationCheck[] };

const LOCAL_MODELS = [
  { id: "qwen3:4b", name: "Qwen 3 4B", note: "Compact · good for lighter laptops · ~2.5 GB download" },
  { id: "qwen3:8b", name: "Qwen 3 8B", note: "Balanced local starter · ~5.2 GB download" },
  { id: "gpt-oss:20b", name: "GPT-OSS 20B", note: "Stronger reasoning · ~14 GB download" },
  { id: "qwen3-coder:30b", name: "Qwen 3 Coder 30B", note: "Coding-focused · ~19 GB download · stronger hardware" },
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
  const [verification, setVerification] = useState<SetupVerification | null>(null);
  const [provider, setProvider] = useState<Provider>("ollama");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [progress, setProgress] = useState<string[]>([]);

  const cloudModels = useMemo(() => provider === "ollama" ? [] : CLOUD_MODELS[provider], [provider]);

  function log(line: string) {
    setProgress((items) => [...items, line]);
  }

  async function verifySetup(logResults = false) {
    const result = await invoke<SetupVerification>("setup_verify");
    setVerification(result);
    setReady(result.ready);
    if (logResults) {
      for (const item of result.checks) {
        log(`${item.status === "ready" ? "✓" : "✗"} ${item.name}: ${item.detail}`);
      }
    }
    return result;
  }

  async function refresh() {
    try {
      const next = await invoke<SetupStatus>("setup_status");
      setStatus(next);
      setProvider(next.provider);
      setModel((current) => next.complete ? next.model : current || next.hardware.recommendedModel || next.model || "qwen3:8b");
      if (next.complete) {
        await verifySetup(false);
      } else {
        setVerification(null);
        setReady(false);
      }
    } catch (err) {
      setReady(false);
      setError(`Genesis Setup must run inside the Windows desktop installer. ${message(err)}`);
    }
  }

  useEffect(() => { void refresh(); }, []);

  function chooseProvider(next: Provider) {
    setProvider(next);
    setReady(false);
    setVerification(null);
    setError("");
    if (next === "ollama") setModel(status?.hardware.recommendedModel || "qwen3:8b");
    if (next === "openai") setModel("gpt-5.6-terra");
    if (next === "anthropic") setModel("claude-sonnet-5");
  }

  async function chooseWorkspace() {
    setBusy(true); setError("");
    try {
      const selected = await invoke<string | null>("setup_choose_workspace");
      if (selected) {
        log(`Project workspace selected: ${selected}`);
        await refresh();
      }
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }

  async function prepareLocal() {
    if (!model) return;
    setBusy(true); setError(""); setReady(false); setVerification(null); setProgress([]);
    try {
      let current = await invoke<SetupStatus>("setup_status");
      if (!current.ollamaInstalled) {
        log("Installing Ollama automatically…");
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
      log("Running final Genesis setup verification…");
      const verified = await verifySetup(true);
      if (!verified.ready) throw new Error("Setup verification found a problem. Review the failed check below and run preparation again.");
      log("All setup checks are green. Genesis is ready.");
      await refresh();
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }

  async function prepareCloud() {
    if (provider === "ollama" || !model) return;
    setBusy(true); setError(""); setReady(false); setVerification(null); setProgress([]);
    try {
      log(`Validating ${model} with the ${provider === "openai" ? "OpenAI" : "Anthropic"} API…`);
      log(await invoke<string>("setup_validate_cloud", { provider, apiKey, model }));
      await invoke("setup_save", { provider, model });
      setApiKey("");
      log("Running final Genesis setup verification…");
      const verified = await verifySetup(true);
      if (!verified.ready) throw new Error("Setup verification found a problem. Review the failed check below and validate again.");
      log("All setup checks are green. Genesis is ready.");
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
      const verified = await verifySetup(false);
      if (!verified.ready) throw new Error("Genesis setup is no longer healthy. Repair the failed check before finishing installation.");
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
              <p>Genesis verifies your AI provider and lets you choose the project folder before installation finishes. Local mode detects your hardware, installs and starts Ollama, then prepares the models. Cloud mode validates both the API key and selected model.</p>
            </div>
            <div className={styles.step}>{status?.installerMode ? "Installer setup" : "First-run / repair"}</div>
          </header>

          <div className={styles.body}>
            {status ? (
              <div className={styles.section}>
                <div className={styles.sectionTitle}>
                  <strong>This PC</strong>
                  <span className={styles.status}>Recommended: {status.hardware.recommendedModel}</span>
                </div>
                <div className={styles.row}>
                  <span className={styles.status}>{status.hardware.totalMemoryGb > 0 ? `${status.hardware.totalMemoryGb} GB RAM` : "RAM unknown"}</span>
                  <span className={styles.status}>{status.hardware.freeDiskGb > 0 ? `${status.hardware.freeDiskGb} GB free` : "Disk space unknown"}</span>
                  <span className={styles.status}>{status.hardware.gpuName}</span>
                </div>
                <p className={styles.note}>Recommendation is conservative and based on total RAM plus free disk space. GPU offload varies by driver and hardware, so Genesis does not pretend a GPU name guarantees a particular model speed.</p>
              </div>
            ) : null}

            <div className={styles.choiceGrid}>
              <button className={`${styles.choice} ${provider === "ollama" ? styles.choiceActive : ""}`} onClick={() => chooseProvider("ollama")} disabled={busy}>
                <strong>Local with Ollama</strong>
                <span>Private local models. Genesis detects Ollama, installs it if needed, starts it, then downloads the models you select.</span>
                <span className={styles.recommended}>Recommended starting point</span>
              </button>
              <button className={`${styles.choice} ${provider !== "ollama" ? styles.choiceActive : ""}`} onClick={() => chooseProvider("openai")} disabled={busy}>
                <strong>Cloud API</strong>
                <span>Use OpenAI or Anthropic without downloading a large local chat model. Genesis validates model access before setup completes.</span>
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
                  {LOCAL_MODELS.map((item) => {
                    const recommended = status?.hardware.recommendedModel === item.id;
                    return (
                      <button key={item.id} className={`${styles.model} ${model === item.id ? styles.modelActive : ""}`} onClick={() => { setModel(item.id); setReady(false); setVerification(null); }} disabled={busy}>
                        <strong>{item.name}{recommended ? " · Recommended" : ""}</strong>
                        <small>{item.note}</small>
                      </button>
                    );
                  })}
                </div>
                <p className={styles.note}>Genesis also prepares the {status?.embeddingModel ?? "nomic-embed-text"} embedding model for memory. You can choose a model above the recommendation; Genesis simply avoids pretending it will be fast on every PC.</p>
              </div>
            ) : (
              <div className={styles.section}>
                <div className={styles.sectionTitle}><strong>1. Cloud provider</strong><span className={styles.status}>Key + model validation required</span></div>
                <div className={styles.row}>
                  <select className={styles.select} value={provider} onChange={(event) => chooseProvider(event.target.value as Provider)} disabled={busy}>
                    <option value="openai">OpenAI</option>
                    <option value="anthropic">Anthropic</option>
                  </select>
                  <select className={styles.select} value={model} onChange={(event) => { setModel(event.target.value); setReady(false); setVerification(null); }} disabled={busy}>
                    {cloudModels.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                  </select>
                </div>
                <div className={styles.row} style={{ marginTop: 10 }}>
                  <input className={styles.input} type="password" autoComplete="off" spellCheck={false} value={apiKey} onChange={(event) => { setApiKey(event.target.value); setReady(false); setVerification(null); }} placeholder={provider === "openai" ? "OpenAI API key" : "Anthropic API key"} />
                </div>
                <p className={styles.note}>The key is never written to setup.json. Genesis verifies access to the selected model, stores the key through the operating-system credential store, and only injects it into the local sidecar process.</p>
              </div>
            )}

            <div className={styles.section}>
              <div className={styles.sectionTitle}>
                <strong>2. Project workspace</strong>
                <span className={`${styles.status} ${status?.workspace ? styles.good : ""}`}>{status?.workspace ? "Project selected" : "Starter workspace"}</span>
              </div>
              <div className={styles.row}>
                <button className={styles.button} onClick={() => void chooseWorkspace()} disabled={busy}>Choose project folder…</button>
                <span className={styles.status}>{status?.workspace ?? "Genesis will create a small starter workspace so Workbench is not empty."}</span>
              </div>
              <p className={styles.note}>The folder picker is native to Windows. Genesis stores only the selected path and verifies that Workbench can read it without writing probe files into your project.</p>
            </div>

            {verification ? (
              <div className={styles.section}>
                <div className={styles.sectionTitle}>
                  <strong>3. Final verification</strong>
                  <span className={`${styles.status} ${verification.ready ? styles.good : styles.warn}`}>{verification.ready ? "All checks green" : "Repair required"}</span>
                </div>
                {verification.checks.map((item) => (
                  <div className={styles.row} key={item.name} style={{ marginTop: 6 }}>
                    <span className={`${styles.status} ${item.status === "ready" ? styles.good : styles.warn}`}>{item.status === "ready" ? "Ready" : "Failed"}</span>
                    <span className={styles.note}><strong>{item.name}</strong> · {item.detail}</span>
                  </div>
                ))}
              </div>
            ) : null}

            {progress.length ? <div className={styles.progress}>{progress.join("\n")}</div> : null}
            {error ? <div className={styles.error}>{error}</div> : null}
            {ready ? <div className={styles.ready}>Every required setup check is green. Workbench can start.</div> : null}

            <div className={styles.actions}>
              <span className={styles.note}>No project mutation or external worker is enabled by setup. Those still use Genesis approval gates.</span>
              <div className={styles.row}>
                <button className={styles.button} onClick={() => void refresh()} disabled={busy}>Check / repair status</button>
                {!ready ? (
                  <button className={styles.primary} onClick={() => void (provider === "ollama" ? prepareLocal() : prepareCloud())} disabled={busy || !model || (provider !== "ollama" && apiKey.trim().length < 12)}>
                    {busy ? "Preparing…" : provider === "ollama" ? "Install / repair local AI" : "Validate / repair cloud AI"}
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
