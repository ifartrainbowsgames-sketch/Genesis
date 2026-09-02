"use client";

import { useEffect } from "react";

export default function SetupGate() {
  useEffect(() => {
    const tauriWindow = window as Window & { __TAURI_INTERNALS__?: unknown };
    if (!tauriWindow.__TAURI_INTERNALS__) return;
    if (window.location.pathname.startsWith("/setup")) return;

    void import("@tauri-apps/api/core")
      .then(({ invoke }) => invoke<{ complete: boolean; installerMode: boolean }>("setup_status"))
      .then((status) => {
        if (!status.complete || status.installerMode) {
          window.location.replace("/setup");
        }
      })
      .catch(() => {
        // Browser/dev mode and a temporarily unavailable native bridge should not brick the UI.
      });
  }, []);

  return null;
}
