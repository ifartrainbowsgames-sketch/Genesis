"use client";

import { useEffect, useState } from "react";

import { getRuntimeInfo } from "../lib/api";

const STARTUP_ROUTED = "genesis-desktop-startup-routed";

type SetupVerification = { ready: boolean; checks: Array<{ name: string; status: string; detail: string }> };

async function waitForApi(attempts = 40) {
  const runtime = await getRuntimeInfo();
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const response = await fetch(`${runtime.apiBase}/health`, { cache: "no-store" });
      if (response.ok) return true;
    } catch {
      // Sidecar can need a moment to bind after Tauri starts it.
    }
    await new Promise((resolve) => window.setTimeout(resolve, 500));
  }
  return false;
}

export default function SetupGate() {
  const [desktopStarting, setDesktopStarting] = useState(false);
  const [startupProblem, setStartupProblem] = useState("");

  useEffect(() => {
    const tauriWindow = window as Window & { __TAURI_INTERNALS__?: unknown };
    if (!tauriWindow.__TAURI_INTERNALS__) return;
    if (window.location.pathname.startsWith("/setup")) return;

    setDesktopStarting(true);
    void import("@tauri-apps/api/core")
      .then(async ({ invoke }) => {
        const status = await invoke<{ complete: boolean; installerMode: boolean }>("setup_status");
        if (!status.complete || status.installerMode) {
          window.location.replace("/setup");
          return;
        }

        const verification = await invoke<SetupVerification>("setup_verify");
        if (!verification.ready) {
          window.location.replace("/setup");
          return;
        }

        const healthy = await waitForApi();
        if (!healthy) {
          setStartupProblem("Genesis is configured, but its local API did not become ready. Open Diagnostics, retry, or reopen Setup to repair the runtime.");
          setDesktopStarting(false);
          return;
        }

        const startupAlreadyRouted = window.sessionStorage.getItem(STARTUP_ROUTED) === "1";
        if (!startupAlreadyRouted && window.location.pathname === "/") {
          window.sessionStorage.setItem(STARTUP_ROUTED, "1");
          window.location.replace("/workbench");
          return;
        }
        setDesktopStarting(false);
      })
      .catch((error) => {
        setStartupProblem(error instanceof Error ? error.message : String(error));
        setDesktopStarting(false);
      });
  }, []);

  if (!desktopStarting && !startupProblem) return null;

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 20000, display: "grid", placeItems: "center",
      background: "#090b0f", color: "#eef2f7", fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
    }}>
      <div style={{ width: "min(520px, calc(100% - 40px))", border: "1px solid #2a313b", borderRadius: 16, background: "#11151b", padding: 24 }}>
        <div style={{ fontSize: 11, letterSpacing: ".14em", textTransform: "uppercase", color: "#7f8c9d", fontWeight: 800 }}>Genesis desktop</div>
        <h2 style={{ margin: "8px 0 8px", fontSize: 23 }}>{startupProblem ? "Genesis needs attention" : "Starting your Workbench…"}</h2>
        <p style={{ margin: 0, color: startupProblem ? "#ffb0b0" : "#97a4b4", lineHeight: 1.6 }}>
          {startupProblem || "Verifying your Genesis setup, starting the private local API, and loading your configured AI provider."}
        </p>
        {startupProblem ? (
          <div style={{ display: "flex", gap: 8, marginTop: 18, flexWrap: "wrap" }}>
            <button onClick={() => window.location.replace("/setup")} style={{ border: "1px solid #5268ab", background: "#293b72", color: "white", borderRadius: 8, padding: "9px 12px", cursor: "pointer" }}>Repair Setup</button>
            <button onClick={() => window.location.replace("/diagnostics")} style={{ border: "1px solid #37404c", background: "#191e25", color: "#e7ebf0", borderRadius: 8, padding: "9px 12px", cursor: "pointer" }}>Diagnostics</button>
            <button onClick={() => window.location.reload()} style={{ border: "1px solid #37404c", background: "#191e25", color: "#e7ebf0", borderRadius: 8, padding: "9px 12px", cursor: "pointer" }}>Retry</button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
