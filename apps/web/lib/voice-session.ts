"use client";

import { API, api, tokenStore } from "./api";

/** One microphone for a whole voice conversation.
 *
 *  Silero VAD (a small speech model running in the browser) decides when someone is speaking.
 *  Each stretch of speech is an "utterance": its audio (plus the 320 ms before it, so the first
 *  syllable isn't clipped) is streamed to the API, which transcribes it with Amazon Transcribe
 *  and fixes code names (WS /api/voice/listen). Without Transcribe, the browser's own speech
 *  recognition supplies the words and the VAD still decides when speech starts and stops.
 *
 *  The mic stays echo-cancelled and open the whole time, so the user can talk at any moment,
 *  including over Sherpa. */

export type SessionEvents = {
  /** speech began (could still be a cough, or Sherpa's own voice leaking into the mic) */
  onSpeechStart: (id: number) => void;
  /** it has lasted long enough to be real speech */
  onSpeechConfirmed: (id: number) => void;
  /** it was too short to be speech */
  onMisfire: (id: number) => void;
  /** the speaker paused; final text follows in onFinal */
  onSpeechEnd: (id: number) => void;
  onPartial: (id: number, text: string) => void;
  /** final text of an utterance; "" when nothing intelligible was said */
  onFinal: (id: number, text: string) => void;
  onError: (message: string) => void;
};

export type VoiceSession = {
  stt: "transcribe" | "browser";
  /** is the user speaking right now? */
  speaking: () => boolean;
  pause: () => void;
  resume: () => void;
  close: () => void;
};

const FRAME_MS = 32; // Silero v5 frames: 512 samples at 16 kHz
const PRE_ROLL_FRAMES = 10; // 320 ms before speech was detected

type MicVADType = Awaited<ReturnType<(typeof import("@ricky0123/vad-web"))["MicVAD"]["new"]>>;

function toPcm16(frame: Float32Array): ArrayBuffer {
  const out = new Int16Array(frame.length);
  for (let i = 0; i < frame.length; i++) {
    const x = Math.max(-1, Math.min(1, frame[i]));
    out[i] = x < 0 ? x * 0x8000 : x * 0x7fff;
  }
  return out.buffer;
}

/** The API's speech socket, or null when it has no Transcribe (then the browser listens). */
async function openTranscribe(repoId: string, ev: SessionEvents): Promise<WebSocket | null> {
  const cfg = await api.voiceConfig().catch(() => null);
  if (cfg?.stt !== "transcribe") return null;
  const url = API.replace(/^http/, "ws") + "/api/voice/listen";
  return new Promise((resolve) => {
    let settled = false;
    const ws = new WebSocket(url);
    ws.binaryType = "arraybuffer";
    const fail = () => {
      if (settled) return;
      settled = true;
      resolve(null);
    };
    const timer = window.setTimeout(() => (ws.close(), fail()), 5000);
    ws.onopen = () => ws.send(JSON.stringify({ token: tokenStore.get(), repo_id: repoId }));
    ws.onerror = fail;
    ws.onclose = () => {
      window.clearTimeout(timer);
      fail();
    };
    ws.onmessage = (m) => {
      const msg = JSON.parse(String(m.data));
      if (msg.type === "ready") {
        settled = true;
        window.clearTimeout(timer);
        resolve(ws);
      } else if (msg.type === "partial") ev.onPartial(msg.id, msg.text);
      else if (msg.type === "final") {
        mark("final", msg.id);
        ev.onFinal(msg.id, msg.text);
      }
      else if (msg.type === "error") {
        if (typeof msg.id === "number") ev.onFinal(msg.id, "");
        if (!settled) fail();
        else if (!msg.id) ev.onError(msg.message);
      }
    };
  });
}

type Recognition = {
  lang: string; interimResults: boolean; continuous: boolean;
  onresult: ((e: { resultIndex: number; results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void) | null;
  onend: (() => void) | null; onerror: ((e: { error: string }) => void) | null;
  start(): void; stop(): void; abort(): void;
};

/** Browser recognition running for the whole session; the VAD marks where each utterance starts. */
function browserWords(ev: SessionEvents) {
  const W = window as unknown as Record<string, new () => Recognition>;
  const Ctor = W.SpeechRecognition ?? W.webkitSpeechRecognition;
  if (!Ctor) return null;
  let results: { text: string; final: boolean }[] = [];
  let base = 0; // first result of the current utterance
  let current = 0; // utterance id being heard
  let on = true;
  let r: Recognition;
  const text = () => results.slice(base).map((x) => x.text).join(" ").replace(/\s+/g, " ").trim();
  const start = () => {
    r = new Ctor();
    r.lang = navigator.language || "en-US";
    r.interimResults = true;
    r.continuous = true;
    const offset = results.length; // a restarted recognizer numbers its results from 0 again
    r.onresult = (e) => {
      for (let i = e.resultIndex; i < e.results.length; i++)
        results[offset + i] = { text: e.results[i][0].transcript, final: e.results[i].isFinal };
      if (current) ev.onPartial(current, text());
    };
    r.onerror = (e) => {
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        on = false;
        ev.onError("Speech recognition is blocked in this browser.");
      }
    };
    r.onend = () => on && start(); // the browser stops after a while: keep it going
    try {
      r.start();
    } catch {
      /* already running */
    }
  };
  start();
  return {
    begin(id: number) {
      current = id;
      base = results.length;
    },
    /** the utterance ended: wait (briefly) for the recognizer to finalize it */
    end(id: number) {
      const t0 = Date.now();
      const check = () => {
        const last = results[results.length - 1];
        if ((last && last.final) || Date.now() - t0 > 900) {
          ev.onFinal(id, text());
          if (current === id) current = 0;
        } else window.setTimeout(check, 60);
      };
      check();
    },
    cancel(id: number) {
      if (current === id) current = 0;
    },
    close() {
      on = false;
      try {
        r.abort();
      } catch {
        /* not running */
      }
    },
  };
}

/** Timing marks for debugging and tests: `window.addEventListener("sherpa:voice", …)`. */
const mark = (type: string, id: number) =>
  window.dispatchEvent(new CustomEvent("sherpa:voice", { detail: { type, id, at: performance.now() } }));

export async function openVoiceSession(repoId: string, ev: SessionEvents): Promise<VoiceSession> {
  // echo cancellation keeps Sherpa's voice (from the speakers) mostly out of the mic
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
  });
  const ws = await openTranscribe(repoId, ev);
  const browser = ws ? null : browserWords(ev);
  if (!ws && !browser) {
    stream.getTracks().forEach((t) => t.stop());
    throw new Error("no-recognition");
  }

  let id = 0;
  let inSpeech = false;
  let closed = false;
  const ring: Float32Array[] = [];
  const send = (data: string | ArrayBuffer) => ws?.readyState === WebSocket.OPEN && ws.send(data);

  const { MicVAD } = await import("@ricky0123/vad-web");
  let vad: MicVADType;
  try {
    vad = await MicVAD.new({
      model: "v5",
      baseAssetPath: "/vad/",
      onnxWASMBasePath: "/vad/",
      getStream: async () => stream,
      pauseStream: async () => {},
      resumeStream: async () => stream,
      positiveSpeechThreshold: 0.6,
      negativeSpeechThreshold: 0.4,
      redemptionMs: 320, // this much silence ends an utterance (the turn logic may wait longer)
      preSpeechPadMs: PRE_ROLL_FRAMES * FRAME_MS,
      minSpeechMs: 220,
      submitUserSpeechOnPause: false,
      startOnLoad: true,
      onFrameProcessed: (_probs, frame) => {
        if (!ws) return;
        if (inSpeech) send(toPcm16(frame));
        else {
          ring.push(frame.slice());
          if (ring.length > PRE_ROLL_FRAMES) ring.shift();
        }
      },
      onSpeechStart: () => {
        inSpeech = true;
        id += 1;
        if (ws) {
          send(JSON.stringify({ type: "start" }));
          for (const f of ring.splice(0)) send(toPcm16(f));
        }
        browser?.begin(id);
        mark("vad-start", id);
        ev.onSpeechStart(id);
      },
      onSpeechRealStart: () => ev.onSpeechConfirmed(id),
      onVADMisfire: () => {
        inSpeech = false;
        send(JSON.stringify({ type: "cancel" }));
        browser?.cancel(id);
        ev.onMisfire(id);
      },
      onSpeechEnd: () => {
        inSpeech = false;
        send(JSON.stringify({ type: "end" }));
        browser?.end(id);
        mark("vad-end", id);
        ev.onSpeechEnd(id);
      },
    });
  } catch (e) {
    ws?.close();
    browser?.close();
    stream.getTracks().forEach((t) => t.stop());
    throw e;
  }

  if (ws)
    ws.addEventListener("close", () => {
      if (!closed) ev.onError("Lost the connection to the speech service.");
    });

  return {
    stt: ws ? "transcribe" : "browser",
    speaking: () => inSpeech,
    pause: () => {
      if (inSpeech) send(JSON.stringify({ type: "cancel" }));
      inSpeech = false;
      void vad.pause();
    },
    resume: () => void vad.start(),
    close: () => {
      closed = true;
      void vad.destroy();
      ws?.close();
      browser?.close();
      stream.getTracks().forEach((t) => t.stop());
    },
  };
}
