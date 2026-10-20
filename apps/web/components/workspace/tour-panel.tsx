"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Clock, MessageSquare, Play, Route, SkipBack, SkipForward, Square } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError, type Tour } from "../../lib/api";
import { CitationChip, useCodeViewer } from "../code-viewer";
import { SherpaAvatar } from "../sherpa";
import { say, stop as stopSpeech, useSpeaking } from "../../lib/voice";
import { cn } from "../../lib/utils";
import { Markdown } from "../markdown";
import { Badge, Button, Input } from "../ui/primitives";
import { CodeBlock, ease, EmptyState, FadeIn, ModeBadge } from "./shared";

const EXAMPLES = ["user signup", "user login", "password reset", "creating an item"];

export function TourPanel({
  repoId,
  busy,
  setBusy,
  seed,
  onSeedUsed,
  onAsk,
}: {
  repoId: string;
  busy: string | null;
  setBusy: (v: string | null) => void;
  seed: string;
  onSeedUsed: () => void;
  onAsk: (q: string) => void;
}) {
  const [flow, setFlow] = useState("user signup");
  const [tour, setTour] = useState<Tour | null>(null);
  // narration: Sherpa reads each stop aloud and opens the code it is talking about
  const [stopAt, setStopAt] = useState<number | null>(null);
  const session = useRef(0);
  const stepRefs = useRef<(HTMLLIElement | null)[]>([]);
  const { open } = useCodeViewer();
  const { provider } = useSpeaking();

  async function narrate(from = -1) {
    if (!tour) return;
    const mine = ++session.current;
    try {
      if (from < 0 && tour.summary) {
        setStopAt(-1);
        await say("tour:intro", `${tour.title}. ${tour.summary}`);
      }
      for (let i = Math.max(0, from); i < tour.steps.length; i++) {
        if (mine !== session.current) return;
        const s = tour.steps[i];
        setStopAt(i);
        stepRefs.current[i]?.scrollIntoView({ behavior: "smooth", block: "center" });
        open(s.file, s.start_line, s.end_line);
        await say(`tour:${i}`, `Stop ${i + 1}: ${s.title}. ${s.explanation || s.caption || ""}`);
      }
      if (mine === session.current) setStopAt(null);
    } catch {
      // stopped, or replaced by a jump to another stop
    }
  }

  function endNarration() {
    session.current++;
    stopSpeech();
    setStopAt(null);
  }

  useEffect(() => endNarration, [tour]); // a new tour, or leaving the tab, ends the old narration

  async function build(f = flow) {
    if (!f.trim() || !repoId) return;
    setBusy("tour");
    try {
      setTour(await api.tour(repoId, f.trim()));
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed to build the tour");
    } finally {
      setBusy(null);
    }
  }

  useEffect(() => {
    if (seed && repoId) {
      setFlow(seed);
      onSeedUsed();
      build(seed);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seed, repoId]);

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="border-b border-border px-4 py-3">
        <div className="mx-auto flex max-w-4xl gap-2">
          <Input
            value={flow}
            onChange={(e) => setFlow(e.target.value)}
            placeholder="What flow should I trace? e.g. user signup, checkout, file upload"
            className="text-sm"
            onKeyDown={(e) => e.key === "Enter" && !busy && build()}
          />
          <Button onClick={() => build()} disabled={!repoId || !!busy || !flow.trim()} size="sm" className="h-9">
            <Route className="size-4" />
            {busy === "tour" ? "Tracing…" : "Build tour"}
          </Button>
        </div>
      </div>

      <div className="scroll-thin flex-1 overflow-y-auto p-4 sm:p-6">
        {!tour ? (
          <EmptyState
            busy={busy === "tour"}
            pose="exploring"
            title="Guided code tours"
            body="Name a feature and Sherpa walks you through the code that runs, in the order it runs: UI, API, logic, data."
          >
            <div className="flex flex-wrap justify-center gap-2">
              {EXAMPLES.map((x) => (
                <button
                  key={x}
                  disabled={!repoId || !!busy}
                  onClick={() => {
                    setFlow(x);
                    build(x);
                  }}
                  className="rounded-md border border-border bg-card px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:border-input hover:text-foreground disabled:opacity-40"
                >
                  {x}
                </button>
              ))}
            </div>
          </EmptyState>
        ) : (
          <div className="mx-auto max-w-4xl space-y-5">
            <FadeIn>
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="mr-auto text-lg font-semibold">{tour.title}</h2>
                <Badge variant="secondary">
                  <Clock /> ~{tour.estimated_minutes} min · {tour.steps.length} stops
                </Badge>
                <ModeBadge mode={tour.mode} model={tour.model} />
                <Button size="sm" variant={stopAt !== null ? "secondary" : "default"} onClick={() => (stopAt !== null ? endNarration() : narrate())}>
                  {stopAt !== null ? <Square className="size-3.5 fill-current" /> : <Play className="size-3.5 fill-current" />}
                  {stopAt !== null ? "Stop" : "Narrate tour"}
                </Button>
              </div>
              {tour.summary && (
                <div className="mt-3 rounded-xl border border-border bg-card p-4">
                  <Markdown text={tour.summary} />
                </div>
              )}
            </FadeIn>

            <ol className="relative space-y-5 border-l border-border pl-6">
              {tour.steps.map((s, i) => (
                <FadeIn key={i} delay={0.05 * i}>
                  <li className="relative" ref={(el) => void (stepRefs.current[i] = el)}>
                    <span
                      className={cn(
                        "absolute -left-[2.15rem] flex h-7 w-7 items-center justify-center rounded-full border text-xs font-semibold transition-colors",
                        stopAt === i ? "border-primary bg-primary text-primary-foreground" : "border-border bg-background"
                      )}
                    >
                      {i + 1}
                    </span>
                    <div
                      className={cn(
                        "overflow-hidden rounded-xl border bg-card transition-[border-color,box-shadow] duration-200",
                        stopAt === i ? "border-primary/60 ring-[3px] ring-primary/15" : "border-border"
                      )}
                    >
                      <div className="space-y-2 border-b border-border px-4 py-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="mr-auto font-medium">{s.title}</p>
                          <CitationChip file={s.file} start={s.start_line} end={s.end_line} />
                        </div>
                        {s.explanation && <Markdown text={s.explanation} className="text-[13px] text-muted-foreground" />}
                      </div>
                      <CodeBlock code={s.code} start={s.start_line} file={s.file} />
                    </div>
                  </li>
                </FadeIn>
              ))}
            </ol>

            {tour.next_questions.length > 0 && (
              <FadeIn delay={0.3}>
                <p className="mb-2 text-xs font-medium text-muted-foreground">Keep going</p>
                <div className="flex flex-wrap gap-2">
                  {tour.next_questions.map((q) => (
                    <button
                      key={q}
                      onClick={() => onAsk(q)}
                      className="inline-flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-left text-xs text-muted-foreground transition-colors hover:text-foreground"
                    >
                      <MessageSquare className="size-3 shrink-0" /> {q}
                    </button>
                  ))}
                </div>
              </FadeIn>
            )}
          </div>
        )}
      </div>
      <AnimatePresence>
        {tour && stopAt !== null && (
          <motion.div
            role="region"
            aria-label="Tour narration"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 12 }}
            transition={{ duration: 0.2, ease }}
            className="fixed bottom-5 left-1/2 z-modal flex w-[min(34rem,calc(100vw-2rem))] -translate-x-1/2 items-center gap-3 rounded-xl border border-border bg-popover px-3 py-2.5 text-popover-foreground shadow-pop"
          >
            <SherpaAvatar />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">
                {stopAt < 0 ? "Introduction" : tour.steps[stopAt]?.title}
              </p>
              <p className="text-[11px] text-muted-foreground">
                {stopAt < 0 ? "Overview" : `Stop ${stopAt + 1} of ${tour.steps.length}`}
                {provider === "polly" ? " · Amazon Polly" : provider === "browser" ? " · browser voice" : ""}
              </p>
            </div>
            <Button size="icon-sm" variant="ghost" aria-label="Previous stop" disabled={stopAt <= 0} onClick={() => narrate(stopAt - 1)}>
              <SkipBack className="size-4" />
            </Button>
            <Button
              size="icon-sm"
              variant="ghost"
              aria-label="Next stop"
              disabled={stopAt >= tour.steps.length - 1}
              onClick={() => narrate(stopAt + 1)}
            >
              <SkipForward className="size-4" />
            </Button>
            <Button size="icon-sm" variant="secondary" aria-label="Stop narration" onClick={endNarration}>
              <Square className="size-3.5 fill-current" />
            </Button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
