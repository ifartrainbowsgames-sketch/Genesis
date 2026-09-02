"use client";

import { useRef, useState } from "react";

import { api, genesisFetch } from "../../lib/api";
import styles from "./voice.module.css";

type Provider = "ollama" | "openai" | "anthropic";
type VoiceTranscription = { text: string; engine: string; model: string; language: string };
type ChatResponse = { provider: Provider; model: string; content: string };
type Turn = { role: "user" | "assistant"; content: string };

const TARGET_SAMPLE_RATE = 16000;

function mergeBuffers(buffers: Float32Array[]): Float32Array {
  const total = buffers.reduce((sum, item) => sum + item.length, 0);
  const merged = new Float32Array(total);
  let offset = 0;
  for (const buffer of buffers) {
    merged.set(buffer, offset);
    offset += buffer.length;
  }
  return merged;
}

function downsample(buffer: Float32Array, inputRate: number, outputRate: number): Float32Array {
  if (inputRate === outputRate) return buffer;
  if (outputRate > inputRate) throw new Error("Output sample rate must not exceed input sample rate");
  const ratio = inputRate / outputRate;
  const length = Math.max(1, Math.round(buffer.length / ratio));
  const result = new Float32Array(length);
  let inputOffset = 0;
  for (let i = 0; i < length; i += 1) {
    const nextOffset = Math.min(buffer.length, Math.round((i + 1) * ratio));
    let sum = 0;
    let count = 0;
    for (let j = inputOffset; j < nextOffset; j += 1) {
      sum += buffer[j];
      count += 1;
    }
    result[i] = count ? sum / count : 0;
    inputOffset = nextOffset;
  }
  return result;
}

function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const bytesPerSample = 2;
  const dataSize = samples.length * bytesPerSample;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);

  const writeAscii = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i += 1) view.setUint8(offset + i, value.charCodeAt(i));
  };

  writeAscii(0, "RIFF");
  view.setUint32(4, 36 + dataSize, true);
  writeAscii(8, "WAVE");
  writeAscii(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * bytesPerSample, true);
  view.setUint16(32, bytesPerSample, true);
  view.setUint16(34, 16, true);
  writeAscii(36, "data");
  view.setUint32(40, dataSize, true);

  let offset = 44;
  for (const sample of samples) {
    const clamped = Math.max(-1, Math.min(1, sample));
    view.setInt16(offset, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
    offset += 2;
  }

  return new Blob([buffer], { type: "audio/wav" });
}

export default function VoicePage() {
  const [provider, setProvider] = useState<Provider>("ollama");
  const [model, setModel] = useState("");
  const [language, setLanguage] = useState("auto");
  const [speakReplies, setSpeakReplies] = useState(true);
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [voiceMeta, setVoiceMeta] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [error, setError] = useState("");

  const streamRef = useRef<MediaStream | null>(null);
  const contextRef = useRef<AudioContext | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const chunksRef = useRef<Float32Array[]>([]);
  const sampleRateRef = useRef(48000);

  async function startRecording() {
    if (recording || busy) return;
    setError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
      const context = new AudioContext();
      const source = context.createMediaStreamSource(stream);
      const processor = context.createScriptProcessor(4096, 1, 1);
      const silent = context.createGain();
      silent.gain.value = 0;

      chunksRef.current = [];
      sampleRateRef.current = context.sampleRate;
      processor.onaudioprocess = (event) => {
        chunksRef.current.push(new Float32Array(event.inputBuffer.getChannelData(0)));
      };

      source.connect(processor);
      processor.connect(silent);
      silent.connect(context.destination);

      streamRef.current = stream;
      contextRef.current = context;
      sourceRef.current = source;
      processorRef.current = processor;
      setRecording(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function stopRecording() {
    if (!recording) return;
    setRecording(false);
    setBusy(true);
    setError("");
    try {
      processorRef.current?.disconnect();
      sourceRef.current?.disconnect();
      streamRef.current?.getTracks().forEach((track) => track.stop());
      await contextRef.current?.close();

      const merged = mergeBuffers(chunksRef.current);
      if (!merged.length) throw new Error("No microphone audio was captured");
      const pcm = downsample(merged, sampleRateRef.current, TARGET_SAMPLE_RATE);
      const wav = encodeWav(pcm, TARGET_SAMPLE_RATE);
      const response = await genesisFetch(`/v1/voice/transcribe?language=${encodeURIComponent(language.trim() || "auto")}`, {
        method: "POST",
        headers: { "Content-Type": "audio/wav" },
        body: wav,
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload?.detail ?? `Voice request failed: ${response.status}`);
      const result = payload as VoiceTranscription;
      setTranscript(result.text);
      setVoiceMeta(`${result.engine} · ${result.model} · ${result.language}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      streamRef.current = null;
      contextRef.current = null;
      sourceRef.current = null;
      processorRef.current = null;
      chunksRef.current = [];
      setBusy(false);
    }
  }

  function speak(text: string) {
    if (!speakReplies || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
  }

  async function askGenesis() {
    const text = transcript.trim();
    if (!text || busy) return;
    setBusy(true);
    setError("");
    const history = [...turns, { role: "user" as const, content: text }];
    setTurns(history);
    try {
      const response = await api<ChatResponse>("/v1/chat", {
        method: "POST",
        body: JSON.stringify({
          provider,
          model: model.trim() || null,
          conversation_id: "genesis-voice",
          use_memory: true,
          messages: history,
        }),
      });
      setTurns((items) => [...items, { role: "assistant", content: response.content }]);
      setTranscript("");
      speak(response.content);
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
          <div className="eyebrow">GENESIS / LOCAL-FIRST VOICE</div>
          <h1>Voice</h1>
        </div>
        <div className="status"><span />{recording ? "recording" : busy ? "working" : "ready"}</div>
      </header>

      {error && <div className="error">{error}</div>}

      <div className={styles.grid}>
        <section className={`panel ${styles.controls}`}>
          <div className="panelTitle"><div><span>01</span> Microphone</div><small>PCM WAV → whisper.cpp</small></div>
          <div className={styles.body}>
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
            <div className={styles.twoCol}>
              <label>
                Speech language
                <input value={language} onChange={(event) => setLanguage(event.target.value)} placeholder="auto / en / de" />
              </label>
              <label>
                Speak replies
                <select value={speakReplies ? "yes" : "no"} onChange={(event) => setSpeakReplies(event.target.value === "yes")}>
                  <option value="yes">yes · OS voice</option>
                  <option value="no">no</option>
                </select>
              </label>
            </div>

            {!recording ? (
              <button className={styles.recordButton} disabled={busy} onClick={startRecording}>Start push-to-talk recording</button>
            ) : (
              <button className={`${styles.recordButton} ${styles.recording}`} onClick={stopRecording}>Stop & transcribe</button>
            )}

            <p className={styles.hint}>Microphone samples are converted to 16 kHz mono PCM in the browser, then sent to your local Genesis API. Transcription uses only the configured whisper.cpp executable and model.</p>
            {voiceMeta && <div className={styles.badge}>{voiceMeta}</div>}

            <label>
              Transcript
              <textarea className={styles.transcript} value={transcript} onChange={(event) => setTranscript(event.target.value)} placeholder="Your transcript appears here. You can edit it before sending." />
            </label>
            <div className={styles.actions}>
              <button className="approveButton" disabled={busy || recording || !transcript.trim()} onClick={askGenesis}>Ask Genesis</button>
              <button disabled={busy} onClick={() => { window.speechSynthesis?.cancel(); setTranscript(""); }}>Clear / stop speech</button>
            </div>
          </div>
        </section>

        <section className={`panel ${styles.conversation}`}>
          <div className="panelTitle"><div><span>02</span> Conversation</div><small>memory · optional OS TTS</small></div>
          <div className={styles.turns}>
            {turns.length === 0 && <div className={styles.empty}>Record a message, inspect the transcript, then send it to Genesis. Replies can be spoken using your operating system&apos;s installed voices.</div>}
            {turns.map((turn, index) => (
              <article key={index} className={`${styles.turn} ${turn.role === "user" ? styles.user : styles.assistant}`}>
                <b>{turn.role === "user" ? "You" : "Genesis"}</b>
                <p>{turn.content}</p>
              </article>
            ))}
          </div>
        </section>
      </div>
    </main>
  );
}
