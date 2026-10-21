"use client";

import { useSyncExternalStore } from "react";
import { api, ApiError } from "./api";

/** Spoken explanations. Amazon Polly through the API when it is configured, otherwise the
 *  browser's built-in voice. One thing speaks at a time: starting a new one stops the last. */

// Polly takes ~0.5s for a sentence but ~17s for a whole answer, so speech goes out a few sentences
// at a time: the first piece is one sentence so sound starts quickly, and the next piece is
// synthesized while the current one plays (one at a time: parallel calls slow each other down).
const FIRST = 120;
const PIECE = 400;

type State = { id: string | null; provider: "polly" | "browser" | null };
let state: State = { id: null, provider: null };
const subs = new Set<() => void>();
const set = (s: Partial<State>) => {
  state = { ...state, ...s };
  subs.forEach((f) => f());
};

let usePolly: boolean | null = null; // null until the first attempt
let run = 0; // bumps on every start/stop, so a stopped narration never resumes
let audio: HTMLAudioElement | null = null;
let audible = false; // sound is coming out right now (not between pieces, not while fetching)

/** Markdown answer → text worth hearing: no code blocks, no markup, citations read as file names. */
export function speakable(md: string): string {
  return md
    .replace(/```[\s\S]*?```/g, " (code shown on screen) ")
    .replace(/\s*\[[^\[\]\s:]+?:L?\d+(?:\s*[-–]\s*L?\d+)?\](?!\()/g, "")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/^\s{0,3}(#{1,6}|>|[-*+]|\d+[.)])\s+/gm, "")
    .replace(/[*_~|]+/g, "")
    .replace(/\s*\n\s*\n\s*/g, ". ")
    .replace(/\s+/g, " ")
    .replace(/\.\s*\./g, ".")
    .trim();
}

function pieces(text: string): string[] {
  const out: string[] = [];
  let cur = "";
  for (const sentence of text.match(/[^.!?]+[.!?]*\s*/g) ?? [text]) {
    const limit = out.length ? PIECE : FIRST;
    if (cur && (cur + sentence).length > limit) {
      out.push(cur.trim());
      cur = "";
    }
    cur += sentence.slice(0, 2800);
  }
  if (cur.trim()) out.push(cur.trim());
  return out;
}

function playBlob(blob: Blob, mine: number): Promise<void> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(blob);
    const a = new Audio(url);
    audio = a;
    const done = (ok: boolean) => {
      URL.revokeObjectURL(url);
      if (audio === a) audio = null;
      ok && mine === run ? resolve() : reject(new Error("stopped"));
    };
    a.onplaying = () => (audible = true);
    a.onended = () => ((audible = false), done(true));
    a.onerror = () => ((audible = false), done(false));
    a.onpause = () => !a.ended && ((audible = false), done(false));
    a.play().catch(() => done(false));
  });
}

function browserSay(text: string, mine: number): Promise<void> {
  return new Promise((resolve, reject) => {
    if (typeof speechSynthesis === "undefined") return reject(new Error("no speech"));
    const u = new SpeechSynthesisUtterance(text);
    const voices = speechSynthesis.getVoices();
    u.voice =
      voices.find((v) => /^en(-|_)/i.test(v.lang) && /(Samantha|Google US English|Ava|Allison)/.test(v.name)) ??
      voices.find((v) => /^en(-|_)US/i.test(v.lang)) ??
      null;
    u.rate = 1.02;
    u.onstart = () => (audible = true);
    u.onend = () => ((audible = false), mine === run ? resolve() : reject(new Error("stopped")));
    u.onerror = () => ((audible = false), reject(new Error("stopped")));
    speechSynthesis.speak(u);
  });
}

async function sayPolly(parts: string[], mine: number): Promise<number> {
  const fetched: Promise<Blob>[] = [];
  const get = (i: number) => {
    if (i < parts.length && !fetched[i]) {
      fetched[i] = api.speak(parts[i]);
      fetched[i].catch(() => {}); // awaited below; a stopped narration may never await it
    }
    return fetched[i];
  };
  for (let i = 0; i < parts.length; i++) {
    let blob: Blob;
    try {
      blob = await get(i);
    } catch (e) {
      // no Polly on this API: the browser voice takes over from this sentence on
      if (e instanceof ApiError && [0, 503].includes(e.status)) {
        usePolly = false;
        return i;
      }
      throw e;
    }
    if (mine !== run) throw new Error("stopped");
    usePolly = true;
    set({ provider: "polly" });
    get(i + 1); // ready by the time this piece ends
    await playBlob(blob, mine);
  }
  return parts.length;
}

/** Speak `text` (markdown is fine). Resolves when finished; rejects if stopped or replaced. */
export async function say(id: string, text: string): Promise<void> {
  stop();
  const mine = ++run;
  set({ id });
  try {
    const parts = pieces(speakable(text));
    const done = usePolly === false ? 0 : await sayPolly(parts, mine);
    if (done < parts.length) set({ provider: "browser" });
    for (const p of parts.slice(done)) {
      if (mine !== run) throw new Error("stopped");
      await browserSay(p, mine);
    }
  } finally {
    if (mine === run) set({ id: null });
  }
}

export function stop() {
  run++;
  audible = false;
  audio?.pause();
  audio = null;
  if (typeof speechSynthesis !== "undefined") speechSynthesis.cancel();
  if (state.id) set({ id: null });
}

/** Which item is speaking right now (null when silent). */
export function useSpeaking(): State {
  return useSyncExternalStore(
    (f) => {
      subs.add(f);
      return () => subs.delete(f);
    },
    () => state,
    () => state
  );
}

/* ── listening: the browser's speech recognition (Chrome, Safari) ── */

type Recognition = {
  lang: string; interimResults: boolean; continuous: boolean;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void) | null;
  onend: (() => void) | null; onerror: ((e: { error: string }) => void) | null;
  start(): void; stop(): void;
};

export function recognitionSupported(): boolean {
  return typeof window !== "undefined" && ("SpeechRecognition" in window || "webkitSpeechRecognition" in window);
}

/** Listen. `onText` gets the running transcript and its separate phrases; `done` resolves with the
 *  final transcript. `continuous` keeps listening across pauses until stop(); `keepSpeaking`
 *  leaves any narration playing (to catch the user talking over it). */
export function listen(
  onText: (text: string, phrases: string[]) => void,
  opts: { continuous?: boolean; keepSpeaking?: boolean } = {}
): { done: Promise<string>; stop: () => void } {
  const W = window as unknown as Record<string, new () => Recognition>;
  const r = new (W.SpeechRecognition ?? W.webkitSpeechRecognition)();
  r.lang = navigator.language || "en-US";
  r.interimResults = true;
  r.continuous = !!opts.continuous;
  let text = "";
  const done = new Promise<string>((resolve, reject) => {
    r.onresult = (e) => {
      const phrases = Array.from(e.results, (res) => res[0].transcript);
      text = phrases.join("");
      onText(text, phrases);
    };
    r.onerror = (e) => (e.error === "no-speech" || e.error === "aborted" ? resolve(text) : reject(new Error(e.error)));
    r.onend = () => resolve(text);
  });
  if (!opts.keepSpeaking) stop(); // don't talk over the user
  r.start();
  return { done, stop: () => r.stop() };
}

const words = (t: string) => t.toLowerCase().replace(/[^a-z0-9' ]+/g, " ").split(/\s+/).filter(Boolean);
const STOP_WORDS = /^(stop|wait|pause|hold on|hang on|sorry|excuse me|sherpa|hey sherpa|no|actually)\b/;

/** Is `heard` the user talking, or the mic picking up Sherpa's own voice (`speaking`)?
 *  Echo repeats the answer's word pairs; a person interrupting says something else. */
export function isUserSpeech(heard: string, speaking: string): boolean {
  const w = words(heard);
  const said = words(speaking);
  if (!w.length) return false;
  if (STOP_WORDS.test(w.join(" ")) && !said.includes(w[0])) return true;
  if (w.length < 3) return false;
  const pairs = new Set(said.slice(1).map((x, i) => `${said[i]} ${x}`));
  const mine = w.slice(1).map((x, i) => `${w[i]} ${x}`);
  const echoed = mine.filter((p) => pairs.has(p)).length;
  return echoed / mine.length < 0.35;
}

/* ── barge-in by sound level: hears the user over Sherpa's own voice ── */

const TICK_MS = 40;

/** Decides, from mic levels (dBFS) sampled every TICK_MS, when the user starts talking over
 *  Sherpa. It first learns how loud Sherpa's own voice is in the mic after echo cancellation
 *  (the loud end of `calibrateMs` of playback), then fires once the mic stays `riseDb` above
 *  that for `holdMs`. The floor drifts slowly so a louder sentence doesn't count as the user. */
export function createVoiceDetector({ calibrateMs = 1200, riseDb = 12, holdMs = 240 } = {}) {
  const cal: number[] = [];
  let floor: number | null = null;
  let loud = 0;
  return (level: number, playing: boolean): boolean => {
    if (floor === null) {
      if (playing) cal.push(level);
      if (cal.length * TICK_MS < calibrateMs) return false;
      cal.sort((x, y) => x - y);
      floor = Math.max(cal[Math.floor(cal.length * 0.9)], -75);
      return false;
    }
    if (level > floor + riseDb) {
      loud += TICK_MS;
      return loud >= holdMs;
    }
    loud = Math.max(0, loud - TICK_MS);
    floor = Math.max(floor + (level - floor) * 0.01, -75);
    return false;
  };
}

/** Watch the mic while Sherpa speaks and call `onVoice` once when the user talks over it.
 *  Uses the browser's echo cancellation, so what the speakers play mostly cancels out.
 *  Rejects if the mic can't be opened; the returned function releases it. */
export async function watchForVoice(onVoice: () => void): Promise<() => void> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: false },
  });
  const ctx = new AudioContext();
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 1024;
  ctx.createMediaStreamSource(stream).connect(analyser);
  const buf = new Float32Array(analyser.fftSize);
  const heard = createVoiceDetector();
  let fired = false;
  const timer = window.setInterval(() => {
    analyser.getFloatTimeDomainData(buf);
    let sum = 0;
    for (const x of buf) sum += x * x;
    const level = 10 * Math.log10(sum / buf.length + 1e-10);
    if (!fired && heard(level, audible)) {
      fired = true;
      onVoice();
    }
  }, TICK_MS);
  return () => {
    window.clearInterval(timer);
    stream.getTracks().forEach((t) => t.stop());
    ctx.close().catch(() => {});
  };
}
