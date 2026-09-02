export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

export type RuntimeInfo = {
  apiBase: string;
  apiToken: string;
  port: number;
};

let runtimePromise: Promise<RuntimeInfo> | null = null;

function browserRuntime(): RuntimeInfo {
  let port = 8000;
  try {
    const parsed = new URL(API_BASE);
    port = parsed.port ? Number(parsed.port) : parsed.protocol === "https:" ? 443 : 80;
  } catch {}
  return { apiBase: API_BASE, apiToken: "", port };
}

export function getRuntimeInfo(): Promise<RuntimeInfo> {
  if (runtimePromise) return runtimePromise;

  runtimePromise = (async () => {
    if (typeof window === "undefined") return browserRuntime();
    const tauriWindow = window as Window & { __TAURI_INTERNALS__?: unknown };
    if (!tauriWindow.__TAURI_INTERNALS__) return browserRuntime();

    const { invoke } = await import("@tauri-apps/api/core");
    const runtime = await invoke<RuntimeInfo>("runtime_info");
    if (!runtime.apiBase.startsWith("http://127.0.0.1:") || !runtime.apiToken || !runtime.port) {
      throw new Error("Genesis desktop returned invalid private runtime information");
    }
    return runtime;
  })();

  return runtimePromise;
}

export async function genesisFetch(path: string, init?: RequestInit): Promise<Response> {
  const runtime = await getRuntimeInfo();
  const headers = new Headers(init?.headers ?? {});
  if (runtime.apiToken) headers.set("X-Genesis-Token", runtime.apiToken);
  return fetch(`${runtime.apiBase}${path}`, { ...init, headers });
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers ?? {});
  headers.set("content-type", "application/json");
  const response = await genesisFetch(path, { ...init, headers });

  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const data = await response.json();
      message = data.detail ?? message;
    } catch {}
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export type StreamEvent =
  | { event: "meta"; data: { provider: string; model: string; memory_context: string[] } }
  | { event: "delta"; data: { text: string } }
  | { event: "done"; data: { model: string } }
  | { event: "error"; data: { message: string } };

export async function streamApi(
  path: string,
  body: unknown,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await genesisFetch(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok || !response.body) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const data = await response.json();
      message = data.detail ?? message;
    } catch {}
    throw new Error(message);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";

    for (const frame of frames) {
      let event = "message";
      const dataLines: string[] = [];
      for (const line of frame.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      }
      if (!dataLines.length) continue;
      const data = JSON.parse(dataLines.join("\n"));
      onEvent({ event, data } as StreamEvent);
    }
  }
}
