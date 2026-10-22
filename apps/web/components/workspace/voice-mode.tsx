"use client";

import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Mic, X } from "lucide-react";
import { Sherpa, type Pose } from "../sherpa";
import { Button } from "../ui/primitives";
import { duck, isAudible, isUserSpeech, preload, say, stop as stopSpeech, useSpeaking } from "../../lib/voice";
import { openVoiceSession, type VoiceSession } from "../../lib/voice-session";
import { cn } from "../../lib/utils";
import { ease } from "./shared";

type Phase = "starting" | "listening" | "thinking" | "speaking" | "paused";

const POSE: Record<Phase, Pose> = {
  starting: "guide",
  listening: "happy",
  thinking: "thinking",
  speaking: "explaining",
  paused: "guide",
};
const LABEL: Record<Phase, string> = {
  starting: "Getting the mic ready…",
  listening: "Listening…",
  thinking: "Reading the code…",
  speaking: "Speaking. Just talk to interrupt",
  paused: "Paused. Tap the mic to talk",
};

/* Turn-taking: how long a pause has to be before Sherpa answers. The speech detector already
   waits ~0.3 s of silence; these come on top. A finished question answers fast; a sentence that
   trails off ("…and", "…the") gets time to continue. */
const PAUSE_QUESTION = 150; // ended with "?"
const PAUSE_SENTENCE = 450; // ended with "." or no punctuation but complete-sounding
const PAUSE_UNFINISHED = 1600; // trailing "and", "so", "the", "um" …
const UNFINISHED = /\b(and|or|but|so|because|then|also|the|a|an|to|of|in|on|at|for|with|about|from|like|is|are|was|does|do|what|which|how|where|when|why|who|that|this|these|my|your|our|its|um|uh|er|hmm)[,.]?$/i;
// Transcribe often ends a spoken question with "." — how it starts says it's a question
const QUESTION = /^(what|where|how|why|who|when|which|whose|does|do|did|is|are|was|were|can|could|should|would|will|has|have|show|explain|tell|walk)\b/i;
const BARGE_AFTER_MS = 500; // talking over Sherpa this long counts as an interruption, words or not
const FILLER_AFTER_MS = 1100; // if the answer isn't back by then, say a short "let me check"
const IDLE_MS = 60_000; // nobody spoke for a minute: pause the mic
const FILLERS = ["Let me check.", "One sec.", "Let me look.", "Okay, looking at the code."];

/** Hands-free conversation with natural turn-taking: one open mic, Silero VAD for when someone
 *  speaks, Amazon Transcribe (or the browser) for the words. Talk any time: over Sherpa to
 *  interrupt (its voice dips as you start, and stops once it's clear you're talking), or while
 *  it's thinking to add to your question. */
export function VoiceMode({
  repoId,
  repoName,
  ask,
  onClose,
}: {
  repoId: string;
  repoName: string;
  /** asks the question in the chat (so the written answer and sources stay there); resolves to the answer */
  ask: (q: string) => Promise<string | null>;
  onClose: () => void;
}) {
  const [phase, setPhaseState] = useState<Phase>("starting");
  const [heard, setHeard] = useState("");
  const [answer, setAnswer] = useState("");
  const [error, setError] = useState("");
  const [hearing, setHearing] = useState(false); // the VAD hears speech right now
  const [stt, setStt] = useState<"transcribe" | "browser" | null>(null);
  const { provider } = useSpeaking();

  // everything the speech callbacks read and write; they outlive any one render
  const s = useRef({
    session: null as VoiceSession | null,
    phase: "starting" as Phase,
    turn: [] as string[], // finished utterances of the question being asked
    live: "", // the utterance being spoken now
    pending: new Set<number>(), // utterances still waiting for their final text
    overSherpa: new Set<number>(), // utterances that began while Sherpa was speaking
    answer: "", // what Sherpa is saying (to tell an echo from the user)
    lastQuestion: "",
    askId: 0, // bumps to discard an answer that's no longer wanted
    filler: 0,
    timers: { end: 0, barge: 0, idle: 0, filler: 0 },
    closed: false,
    gen: 0, // bumps on every start and shutdown, so a start that was overtaken closes its own mic
  }).current;

  const setPhase = (p: Phase) => {
    s.phase = p;
    setPhaseState(p);
  };
  const clear = (k: keyof typeof s.timers) => window.clearTimeout(s.timers[k]);
  const showHeard = () => setHeard([...s.turn, s.live].filter(Boolean).join(" "));

  function idle() {
    clear("idle");
    s.timers.idle = window.setTimeout(() => {
      if (s.phase !== "listening" || s.turn.length || s.live) return;
      s.session?.pause();
      setPhase("paused");
    }, IDLE_MS);
  }

  function listenNow() {
    duck(false);
    setPhase("listening");
    showHeard();
    idle();
  }

  /** The user is talking over Sherpa: stop speaking and take their words as the next question. */
  function barge(id: number) {
    if (s.phase !== "speaking") return;
    clear("barge");
    s.overSherpa.delete(id);
    s.askId++; // the answer loop must not resume listening on its own
    stopSpeech();
    s.turn = [];
    listenNow();
  }

  /** Answer once the pause after the last utterance is long enough for what was said. */
  function maybeEndTurn() {
    clear("end");
    if (s.phase !== "listening" || s.session?.speaking() || s.pending.size) return;
    const text = s.turn.join(" ").trim();
    if (!text) return;
    const wait = UNFINISHED.test(text)
      ? PAUSE_UNFINISHED
      : /\?$/.test(text) || QUESTION.test(text)
        ? PAUSE_QUESTION
        : PAUSE_SENTENCE;
    s.timers.end = window.setTimeout(submit, wait);
  }

  async function submit() {
    clear("end");
    const q = s.turn.join(" ").trim();
    if (!q || s.phase !== "listening") return;
    s.turn = [];
    s.live = "";
    s.lastQuestion = q;
    setHeard(q);
    setAnswer("");
    setError("");
    setPhase("thinking");
    clear("idle");
    const mine = ++s.askId;
    let filler: Promise<void> = Promise.resolve();
    s.timers.filler = window.setTimeout(() => {
      if (mine !== s.askId || s.phase !== "thinking") return;
      filler = say("voice-filler", FILLERS[s.filler++ % FILLERS.length]).catch(() => {});
    }, FILLER_AFTER_MS);

    const a = await ask(q);
    clear("filler");
    if (mine !== s.askId || s.closed) return; // they kept talking: a newer question replaced this
    if (!a) {
      setError("Something went wrong answering that. Try again.");
      return listenNow();
    }
    await filler;
    if (mine !== s.askId || s.closed) return;
    s.answer = a;
    setAnswer(a);
    setPhase("speaking");
    try {
      await say("voice-mode", a);
    } catch {
      // stopped: interrupted by voice or a tap
    }
    if (mine === s.askId && !s.closed) listenNow(); // finished on its own: your turn
  }

  async function start() {
    const gen = ++s.gen;
    setError("");
    setPhase("starting");
    try {
      const session = await openVoiceSession(repoId, {
        onSpeechStart: (id) => {
          setHearing(true);
          clear("end");
          clear("idle");
          if (s.phase === "speaking") {
            s.overSherpa.add(id);
            duck(true); // dip, like a person pausing to listen
            clear("barge");
            s.timers.barge = window.setTimeout(() => barge(id), BARGE_AFTER_MS);
          }
          s.pending.add(id);
        },
        onSpeechConfirmed: () => {
          // (not while the "let me check" filler plays: that's likely its own echo)
          if (s.phase === "thinking" && !isAudible()) {
            // adding to the question while Sherpa thinks: drop that answer, keep listening
            s.askId++;
            clear("filler");
            stopSpeech();
            s.turn = s.lastQuestion ? [s.lastQuestion] : [];
            listenNow();
          }
        },
        onMisfire: (id) => {
          setHearing(false);
          s.pending.delete(id);
          if (s.overSherpa.delete(id)) {
            clear("barge");
            duck(false); // a cough or a click: carry on
          }
          maybeEndTurn();
        },
        onSpeechEnd: (id) => {
          setHearing(false);
          if (s.overSherpa.has(id)) clear("barge"); // too short to be sure; the words decide
        },
        onPartial: (id, text) => {
          if (!s.pending.has(id)) return; // arrived after its final text
          if (s.overSherpa.has(id)) {
            if (isUserSpeech(text, s.answer)) barge(id);
            return;
          }
          if (s.phase !== "listening") return;
          s.live = text;
          showHeard();
        },
        onFinal: (id, text) => {
          s.pending.delete(id);
          if (s.overSherpa.has(id)) {
            s.overSherpa.delete(id);
            if (text && isUserSpeech(text, s.answer)) barge(id);
            else if (s.phase === "speaking") {
              duck(false); // it was Sherpa's own voice: carry on
              return;
            } else return;
          }
          if (s.phase !== "listening") return;
          s.live = "";
          if (text) s.turn.push(text);
          showHeard();
          maybeEndTurn();
        },
        onError: (message) => setError(message),
      });
      if (s.closed || gen !== s.gen) return session.close(); // closed (or restarted) while the mic opened
      s.session = session;
      setStt(session.stt);
      preload(FILLERS);
      listenNow();
    } catch (e) {
      if (gen !== s.gen) return;
      const m = e instanceof Error ? `${e.name} ${e.message}` : "";
      setError(
        /NotAllowed|Permission|not-allowed/.test(m)
          ? "Microphone access is blocked. Allow it in your browser or System Settings."
          : /no-recognition/.test(m)
            ? "This browser can't recognize speech, and the server has no speech service configured."
            : "Couldn't start the microphone."
      );
      setPhase("paused");
    }
  }

  function tap() {
    if (s.phase === "speaking") {
      s.askId++;
      stopSpeech();
      s.turn = [];
      listenNow();
    } else if (s.phase === "listening") {
      if (s.live) s.turn.push(s.live), (s.live = "");
      if (s.turn.length) {
        s.pending.clear();
        void submit(); // done talking: answer now
      }
    } else if (s.phase === "paused") {
      if (s.session) {
        s.session.resume();
        listenNow();
      } else void start();
    }
  }

  function shutdown() {
    s.closed = true;
    s.gen++;
    s.askId++;
    Object.values(s.timers).forEach((t) => window.clearTimeout(t));
    s.session?.close();
    s.session = null;
    stopSpeech();
  }

  function close() {
    shutdown();
    onClose();
  }

  useEffect(() => {
    s.closed = false;
    void start();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      shutdown();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const voice = provider === "polly" ? "Amazon Polly" : provider === "browser" ? "browser voice" : "";
  const ears = stt === "transcribe" ? "Amazon Transcribe" : stt === "browser" ? "browser speech recognition" : "";

  return (
    <motion.div
      role="dialog"
      aria-modal
      aria-label="Voice conversation"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.2, ease }}
      className="fixed inset-0 z-modal flex flex-col bg-background"
    >
      <header className="flex items-center justify-between px-5 py-4">
        <div>
          <p className="text-sm font-medium">Voice conversation</p>
          <p className="text-xs text-muted-foreground">
            {[repoName, ears, voice].filter(Boolean).join(" · ")}
          </p>
        </div>
        <Button variant="ghost" size="icon-sm" onClick={close} aria-label="End voice conversation">
          <X className="size-4" />
        </Button>
      </header>

      <div className="flex flex-1 flex-col items-center justify-center gap-6 px-6 text-center">
        <motion.div
          key={phase}
          initial={{ scale: 0.96, opacity: 0.6 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 0.25, ease }}
        >
          <Sherpa pose={POSE[phase]} size={168} decorative />
        </motion.div>
        <p className="eyebrow" aria-live="polite">
          {LABEL[phase]}
        </p>
        <div className="min-h-[5.5rem] w-full max-w-2xl">
          {phase === "listening" || phase === "thinking" || phase === "starting" ? (
            <p className={cn("text-xl font-medium leading-snug", !heard && "text-muted-foreground")}>
              {heard || (phase === "listening" ? "Ask anything about this codebase" : "")}
            </p>
          ) : answer ? (
            <p className="scroll-thin mx-auto max-h-48 overflow-y-auto text-base leading-relaxed text-muted-foreground">
              {answer.replace(/\s*\[[^\]\s:]+:\d+(?:[-–]\d+)?\]/g, "")}
            </p>
          ) : null}
          {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
        </div>
      </div>

      <div className="pb-safe flex flex-col items-center gap-3 pb-10">
        <button
          type="button"
          onClick={tap}
          aria-label={phase === "listening" ? "Done talking" : phase === "speaking" ? "Interrupt" : "Talk"}
          className={cn(
            "relative flex size-16 items-center justify-center rounded-full transition-[background-color,transform] duration-150 active:scale-95",
            phase === "listening" ? "bg-primary text-primary-foreground" : "bg-secondary text-foreground hover:bg-accent"
          )}
        >
          {phase === "listening" && (
            <span
              className={cn(
                "absolute inset-0 rounded-full border-2 border-primary",
                hearing ? "scale-110 opacity-90 transition-transform duration-150" : "motion-safe:animate-ping"
              )}
              aria-hidden
            />
          )}
          <Mic className="size-6" />
        </button>
        <p className="text-[11px] text-muted-foreground">
          Talk any time, even over Sherpa · answers and sources are saved in the chat · Esc to end
        </p>
      </div>
    </motion.div>
  );
}
