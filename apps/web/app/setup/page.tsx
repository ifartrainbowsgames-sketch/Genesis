"use client";

import { useEffect, useMemo, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import styles from "./setup-v2.module.css";

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
type OllamaProbe = {
  installed: boolean;
  running: boolean;
  path?: string | null;
  models: string[];
};
type VerificationCheck = { name: string; status: "ready" | "failed"; detail: string };
type SetupVerification = { ready: boolean; checks: VerificationCheck[] };

type LocalModel = { id: string; name: string; note: string };

const LOCAL_MODELS: LocalModel[] = [
  { id: "qwen3:4b", name: "Qwen 3 4B", note: "Lightweight" },
  { id: "qwen3:8b", name: "Qwen 3 8B", note: "Balanced" },
  { id: "gpt-oss:20b", name: "GPT-OSS 20B", note: "Stronger reasoning" },
  { id: "qwen3-coder:30b", name: "Qwen 3 Coder 30B", note: "Coding focused" },
];

const CLOUD_MODELS: Record<Exclude<Provider, "ollama">, Array<{ id: string; name: string }>> = {
  openai: [
    { id: "gpt-5.6-terra", name: "GPT-5.6 Terra" },
    { id: "gpt-5.6-sol", name: "GPT-5.6 Sol" },
    { id: "gpt-5.6-luna", name: "GPT-5.6 Luna" },
  ],
  anthropic: [{ id: "claude-sonnet-5", name: "Claude Sonnet 5" }],
};

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

function canonicalModel(name: string) {
  const lower = name.trim().toLowerCase();
  const last = lower.split("/").pop() ?? lower;
  return last.includes(":") ? lower : `${lower}:latest`;
}

function modelPresent(models: string[], requested: string) {
  const target = canonicalModel(requested);
  return models.some((model) => canonicalModel(model) === target);
}

export default function SetupPage() {
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [probe, setProbe] = useState<OllamaProbe>({ installed: false, running: false, path: null, models: [] });
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

  async function readProbe() {
    try {
      const result = await invoke<OllamaProbe>("setup_ollama_probe");
      setProbe(result);
      return result;
    } catch {
      const fallback = { installed: false, running: false, path: null, models: [] } satisfies OllamaProbe;
      setProbe(fallback);
      return fallback;
    }
  }

  async function verifySetup(logChecks = false) {
    const result = await invoke<SetupVerification>("setup_verify");
    setVerification(result);
    setReady(result.ready);
    if (logChecks) {
      for (const item of result.checks) log(`${item.status === "ready" ? "✓" : "✗"} ${item.name}: ${item.detail}`);
    }
    return result;
  }

  async function refresh() {
    setError("");
    try {
      const [next, detected] = await Promise.all([
        invoke<SetupStatus>("setup_status"),
        readProbe(),
      ]);
      setStatus({ ...next, ollamaInstalled: detected.installed, ollamaRunning: detected.running });
      setProvider(next.provider);
      setModel((current) => next.complete ? next.model : current || next.hardware.recommendedModel || next.model || "qwen3:8b");
      if (next.complete) await verifySetup(false);
      else {
        setVerification(null);
        setReady(false);
      }
    } catch (err) {
      setReady(false);
      setError(`Genesis Setup must run inside the Windows desktop app. ${errorMessage(err)}`);
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
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const selected = await invoke<string | null>("setup_choose_workspace");
      if (selected) log(`Workspace: ${selected}`);
      await refresh();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function prepareLocal() {
    if (!model || busy) return;
    setBusy(true);
    setError("");
    setReady(false);
    setVerification(null);
    setProgress([]);
    try {
      let detected = await readProbe();
      if (!detected.installed) {
        log("Ollama was not found. Installing it now…");
        log(await invoke<string>("setup_install_ollama"));
        detected = await readProbe();
      } else {
        log(`Existing Ollama found${detected.path ? ` at ${detected.path}` : ""}.`);
      }

      if (!detected.running) {
        log("Starting Ollama…");
        log(await invoke<string>("setup_ollama_start_existing"));
        detected = await readProbe();
      } else {
        log("Ollama is already running.");
      }

      if (modelPresent(detected.models, model)) log(`${model} is already installed — Genesis will reuse it.`);
      if (modelPresent(detected.models, "nomic-embed-text")) log("nomic-embed-text is already installed — Genesis will reuse it.");
      log(await invoke<string>("setup_ollama_prepare_models", { model }));

      await invoke("setup_save", { provider: "ollama", model });
      log("Checking Genesis…");
      const verified = await verifySetup(true);
      if (!verified.ready) throw new Error("Setup verification found a problem. Review the failed check and retry.");
      log("Genesis is ready.");
      await refresh();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function prepareCloud() {
    if (provider === "ollama" || !model || busy) return;
    setBusy(true);
    setError("");
    setReady(false);
    setVerification(null);
    setProgress([]);
    try {
      log(`Validating ${model}…`);
      log(await invoke<string>("setup_validate_cloud", { provider, apiKey, model }));
      await invoke("setup_save", { provider, model });
      setApiKey("");
      const verified = await verifySetup(true);
      if (!verified.ready) throw new Error("Setup verification found a problem. Review the failed check and retry.");
      log("Genesis is ready.");
      await refresh();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function finish() {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const verified = await verifySetup(false);
      if (!verified.ready) throw new Error("Genesis setup needs repair before it can start.");
      await invoke("setup_finish");
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  const hardware = status?.hardware;
  const detectedLabel = probe.installed
    ? `${probe.running ? "Ollama is running" : "Ollama is installed"}${probe.path ? ` · ${probe.path}` : ""}`
    : "Ollama is not installed. Genesis can install it automatically.";

  return (
    <main className={styles.overlay}>
      <section className={styles.window}>
        <header className={styles.header}>
          <div className={styles.kicker}>Genesis 0.10 · {status?.installerMode ? "Windows setup" : "Setup & repair"}</div>
          <h1>Set up Genesis</h1>
          <p>Choose local or cloud AI and a project folder. Genesis detects what is already on this PC and reuses it instead of reinstalling or redownloading it.</p>
        </header>

        <div className={styles.body}>
          <div className={styles.detected}>
            <div>
              <strong>This PC</strong>
              <span>{hardware?.totalMemoryGb ? `${hardware.totalMemoryGb} GB RAM · ` : ""}{hardware?.freeDiskGb ? `${hardware.freeDiskGb} GB free · ` : ""}{hardware?.gpuName || "Hardware detection in progress"}</span>
              <span className={probe.installed ? styles.good : styles.warn}>{detectedLabel}</span>
            </div>
            {hardware?.recommendedModel ? <span>Recommended<br /><strong>{hardware.recommendedModel}</strong></span> : null}
          </div>

          <div className={styles.step}>
            <div className={styles.stepTitle}><span className={styles.stepNumber}>1</span><strong>AI</strong></div>
            <div className={styles.choices}>
              <button className={`${styles.choice} ${provider === "ollama" ? styles.choiceActive : ""}`} type="button" onClick={() => chooseProvider("ollama")} disabled={busy}>
                <strong>Local</strong><span>Use Ollama on this PC. Existing installation and models are reused automatically.</span>
              </button>
              <button className={`${styles.choice} ${provider !== "ollama" ? styles.choiceActive : ""}`} type="button" onClick={() => chooseProvider("openai")} disabled={busy}>
                <strong>Cloud</strong><span>Use an OpenAI or Anthropic API key stored in the Windows credential vault.</span>
              </button>
            </div>
          </div>

          {provider === "ollama" ? (
            <div className={styles.step}>
              <div className={styles.stepTitle}><span className={styles.stepNumber}>2</span><strong>Local model</strong></div>
              <div className={styles.models}>
                {LOCAL_MODELS.map((item) => {
                  const installed = modelPresent(probe.models, item.id);
                  const recommended = hardware?.recommendedModel === item.id;
                  return (
                    <button key={item.id} className={`${styles.model} ${model === item.id ? styles.modelActive : ""}`} type="button" onClick={() => { setModel(item.id); setReady(false); }} disabled={busy}>
                      <strong>{item.name}{recommended ? " · Recommended" : ""}</strong>
                      <span className={installed ? styles.installed : ""}>{installed ? "Already installed" : item.note}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className={styles.step}>
              <div className={styles.stepTitle}><span className={styles.stepNumber}>2</span><strong>Cloud access</strong></div>
              <div className={styles.fields}>
                <select className={styles.select} value={provider} onChange={(event) => chooseProvider(event.target.value as Provider)} disabled={busy}>
                  <option value="openai">OpenAI</option>
                  <option value="anthropic">Anthropic</option>
                </select>
                <select className={styles.select} value={model} onChange={(event) => setModel(event.target.value)} disabled={busy}>
                  {cloudModels.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}
                </select>
                <input className={styles.input} style={{ gridColumn: "1 / -1" }} type="password" autoComplete="off" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder="API key" disabled={busy} />
              </div>
            </div>
          )}

          <div className={styles.step}>
            <div className={styles.stepTitle}><span className={styles.stepNumber}>3</span><strong>Project</strong></div>
            <div className={styles.workspace}>
              <button className={styles.secondary} type="button" onClick={() => void chooseWorkspace()} disabled={busy}>Choose folder…</button>
              <span className={styles.workspacePath} title={status?.workspace ?? undefined}>{status?.workspace ?? "No project selected · Genesis will use its starter workspace"}</span>
            </div>
          </div>

          {verification ? (
            <div className={styles.verification} aria-live="polite">
              {verification.checks.map((check) => (
                <div className={styles.check} key={check.name}>
                  <span className={check.status === "ready" ? styles.checkReady : styles.warn}>{check.status === "ready" ? "✓" : "!"}</span>
                  <span>{check.name} · {check.detail}</span>
                </div>
              ))}
            </div>
          ) : null}

          {progress.length ? <div className={styles.progress}>{progress.join("\n")}</div> : null}
          {error ? <div className={styles.error} role="alert">{error}</div> : null}

          <footer className={styles.footer}>
            <span className={styles.footerNote}>Genesis never writes API keys to setup.json. Local model downloads come from Ollama only when the requested model is missing.</span>
            {ready ? (
              <button className={styles.primary} type="button" onClick={() => void finish()} disabled={busy}>{status?.installerMode ? "Finish installation" : "Open Workbench"}</button>
            ) : (
              <button className={styles.primary} type="button" onClick={() => void (provider === "ollama" ? prepareLocal() : prepareCloud())} disabled={busy || !model || (provider !== "ollama" && apiKey.trim().length < 12)}>{busy ? "Preparing…" : "Continue"}</button>
            )}
          </footer>
        </div>
      </section>
    </main>
  );
}
