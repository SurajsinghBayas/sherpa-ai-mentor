"use client";

import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Mic, X } from "lucide-react";
import { Sherpa, type Pose } from "../sherpa";
import { Button } from "../ui/primitives";
import { isUserSpeech, listen, say, stop as stopSpeech, useSpeaking } from "../../lib/voice";
import { cn } from "../../lib/utils";
import { ease } from "./shared";

type Phase = "listening" | "thinking" | "speaking" | "paused";

const POSE: Record<Phase, Pose> = { listening: "happy", thinking: "thinking", speaking: "explaining", paused: "guide" };
const LABEL: Record<Phase, string> = {
  listening: "Listening…",
  thinking: "Reading the code…",
  speaking: "Speaking. Talk or tap to interrupt",
  paused: "Tap the mic to talk",
};

/** Hands-free conversation: listen → answer → speak → listen again, until closed.
 *  Tapping the mic while Sherpa speaks interrupts it and listens right away. */
export function VoiceMode({
  repoName,
  ask,
  onClose,
}: {
  repoName: string;
  /** asks the question in the chat (so the written answer and sources stay there); resolves to the answer */
  ask: (q: string) => Promise<string | null>;
  onClose: () => void;
}) {
  const [phase, setPhase] = useState<Phase>("paused");
  const [heard, setHeard] = useState("");
  const [answer, setAnswer] = useState("");
  const [error, setError] = useState("");
  const loopId = useRef(0);
  const rec = useRef<{ stop: () => void } | null>(null);
  const { provider } = useSpeaking();

  async function converse() {
    const mine = ++loopId.current;
    const live = () => mine === loopId.current;
    setError("");
    let misses = 0;
    let next = ""; // a question caught while Sherpa was talking
    while (live()) {
      let q = next;
      next = "";
      if (!q) {
        setPhase("listening");
        setHeard("");
        try {
          const r = listen(setHeard);
          rec.current = r;
          q = (await r.done).trim();
        } catch (e) {
          if (!live()) return;
          setError(
            e instanceof Error && /not-allowed|service-not-allowed/.test(e.message)
              ? "Microphone access is blocked. Allow it in your browser or System Settings."
              : "I couldn't hear that."
          );
          return setPhase("paused");
        } finally {
          rec.current = null;
        }
        if (!live()) return;
        if (!q) {
          if (++misses >= 2) return setPhase("paused"); // nobody's talking: wait for a tap
          continue;
        }
      }
      misses = 0;
      setPhase("thinking");
      setAnswer("");
      const a = await ask(q);
      if (!live()) return;
      if (!a) {
        setError("Something went wrong answering that. Try again.");
        return setPhase("paused");
      }
      setAnswer(a);
      setPhase("speaking");
      next = await speakInterruptibly(a, live);
    }
  }

  /** Speak `a` while listening for the user talking over it. Returns what they said if they
   *  interrupted (it becomes the next question), or "" when Sherpa finished or was tapped. */
  async function speakInterruptibly(a: string, live: () => boolean): Promise<string> {
    let barged = false;
    let from = 0;
    let said = "";
    let quiet: ReturnType<typeof setTimeout> | undefined;
    let watcher: { done: Promise<string>; stop: () => void } | null = null;
    try {
      watcher = listen(
        (_, phrases) => {
          if (!barged) {
            const latest = phrases[phrases.length - 1] ?? "";
            if (!isUserSpeech(latest, a)) return; // Sherpa hearing itself
            barged = true;
            from = phrases.length - 1;
            stopSpeech();
            setPhase("listening");
          }
          said = phrases.slice(from).join(" ").trim();
          setHeard(said);
          clearTimeout(quiet);
          quiet = setTimeout(() => watcher?.stop(), 1200); // a pause ends the question
        },
        { continuous: true, keepSpeaking: true }
      );
      rec.current = watcher;
    } catch {
      watcher = null; // no recognition: tap to interrupt still works
    }
    try {
      await say("voice-mode", a);
    } catch {
      // interrupted by voice or by a tap
    }
    if (!barged || !live()) {
      clearTimeout(quiet);
      watcher?.stop();
      await watcher?.done.catch(() => "");
      rec.current = null;
      return "";
    }
    await watcher?.done.catch(() => "");
    clearTimeout(quiet);
    rec.current = null;
    return said;
  }

  function tap() {
    if (phase === "listening") rec.current?.stop(); // done talking: send what was heard
    else if (phase === "speaking") stopSpeech(); // the loop moves straight on to listening
    else if (phase === "paused") converse();
  }

  function close() {
    loopId.current++;
    rec.current?.stop();
    stopSpeech();
    onClose();
  }

  useEffect(() => {
    converse();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      loopId.current++;
      rec.current?.stop();
      stopSpeech();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
            {repoName}
            {provider === "polly" ? " · Amazon Polly" : provider === "browser" ? " · browser voice" : ""}
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
          {phase === "listening" || phase === "thinking" ? (
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
            <span className="absolute inset-0 rounded-full border-2 border-primary motion-safe:animate-ping" aria-hidden />
          )}
          <Mic className="size-6" />
        </button>
        <p className="text-[11px] text-muted-foreground">Answers and sources are also saved in the chat · Esc to end</p>
      </div>
    </motion.div>
  );
}
