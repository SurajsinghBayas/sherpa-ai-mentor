"use client";

import { useEffect, useState } from "react";
import { Clock, MessageSquare, Route } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError, type Tour } from "../../lib/api";
import { CitationChip } from "../code-viewer";
import { Markdown } from "../markdown";
import { Badge, Button, Input } from "../ui/primitives";
import { CodeBlock, EmptyState, FadeIn, ModeBadge } from "./shared";

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

      <div className="custom-scroll flex-1 overflow-y-auto p-4 sm:p-6">
        {!tour ? (
          <EmptyState
            busy={busy === "tour"}
            title="Guided code tours"
            body="Name a feature and Sherpa walks you through the code that runs, in execution order — UI → API → logic → data."
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
                  className="rounded-full border border-border px-3 py-1 text-xs text-muted-foreground transition-colors hover:text-foreground disabled:opacity-40"
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
                <Badge variant="secondary" className="text-[10px]">
                  <Clock /> ~{tour.estimated_minutes} min · {tour.steps.length} stops
                </Badge>
                <ModeBadge mode={tour.mode} model={tour.model} />
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
                  <li className="relative">
                    <span className="absolute -left-[2.15rem] flex h-7 w-7 items-center justify-center rounded-full border border-border bg-background text-xs font-semibold">
                      {i + 1}
                    </span>
                    <div className="overflow-hidden rounded-xl border border-border bg-card">
                      <div className="space-y-2 border-b border-border px-4 py-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="mr-auto font-medium">{s.title}</p>
                          <CitationChip file={s.file} start={s.start_line} end={s.end_line} />
                        </div>
                        {s.explanation && <Markdown text={s.explanation} className="text-[13px] text-muted-foreground" />}
                      </div>
                      <CodeBlock code={s.code} start={s.start_line} />
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
    </div>
  );
}
