"use client";

import { useState } from "react";
import { Cog, MessageSquare, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError, type Pipeline } from "../../lib/api";
import { speakable } from "../../lib/voice";
import { CitationChip } from "../code-viewer";
import { Machine } from "../machine/machine";
import { PART_OF, ROLE_OF } from "../machine/machine-parts";
import { Markdown } from "../markdown";
import { Button } from "../ui/primitives";
import { cn } from "../../lib/utils";
import { EmptyState, FadeIn, ModeBadge, SectionLabel, VerifiedBadge } from "./shared";

const KIND_LABEL: Record<Pipeline["kind"], string> = {
  agent: "Agent loop", rag: "Retrieval + generation", ml: "ML pipeline", workflow: "Workflow", app: "Request path",
};

export function MachinePanel({
  repoId,
  busy,
  setBusy,
  onAsk,
}: {
  repoId: string;
  busy: string | null;
  setBusy: (v: string | null) => void;
  onAsk: (q: string) => void;
}) {
  const [data, setData] = useState<Pipeline | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  async function generate(refresh = false) {
    setBusy("pipeline");
    try {
      const p = await api.pipeline(repoId, refresh);
      setData(p);
      setSelected(p.stages[0]?.id ?? null);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed to map the pipeline");
    } finally {
      setBusy(null);
    }
  }

  if (!data || !data.found) {
    return (
      <div className="scroll-thin flex-1 overflow-y-auto p-6">
        <EmptyState
          busy={busy === "pipeline"}
          pose="analyzing"
          title={data ? "No pipeline found" : "Pipeline machine"}
          body={
            data
              ? "Sherpa didn't find an agent loop, ML pipeline or workflow in this code. Try the Architecture map for how the parts connect."
              : "See how this repo's agent loop, ML pipeline or workflow runs, drawn as a small machine: one part per stage, pipes for what flows between them. Press run to watch it work; click any part to read its code."
          }
        >
          {!data && (
            <Button onClick={() => generate()} disabled={!repoId || !!busy}>
              <Cog className="size-4" />
              {busy === "pipeline" ? "Reading the pipeline…" : "Build the machine"}
            </Button>
          )}
          {!repoId && <p className="text-xs text-muted-foreground">Index a repo first.</p>}
        </EmptyState>
      </div>
    );
  }

  const n = data.stages.findIndex((s) => s.id === selected);
  const stage = data.stages[n];
  const types = [...new Set(data.stages.map((s) => s.type))];
  const into = data.links.filter((l) => l.to === stage?.id);
  const out = data.links.filter((l) => l.from === stage?.id);
  const name = (id: string) => data.stages.find((s) => s.id === id)?.name ?? id;

  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-6xl space-y-6 p-4 sm:p-6">
        <FadeIn>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="mr-auto text-lg font-semibold">{data.title}</h2>
            <ModeBadge mode={data.mode} model={data.model} />
            <VerifiedBadge n={data.citations.length} dropped={data.dropped.length} />
            <Button size="sm" variant="ghost" onClick={() => generate(true)} disabled={!!busy}>
              <RefreshCw className={cn("size-3.5", busy === "pipeline" && "animate-spin")} /> Rebuild
            </Button>
          </div>
          <p className="mt-1.5 text-[13px] text-muted-foreground">
            {KIND_LABEL[data.kind]} · {data.stages.length} stages
            {data.source && <> · mapped from {data.source}</>}
          </p>
          {data.summary && <Markdown text={data.summary} className="mt-3 text-[14px]" />}
        </FadeIn>

        <FadeIn delay={0.05} className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
          <Machine
            title={data.title}
            stages={data.stages}
            links={data.links}
            selected={selected}
            onSelect={setSelected}
            narration={{
              intro: data.intro || speakable(data.summary).split(/(?<=[.!?])\s/)[0],
              lines: Object.fromEntries(data.stages.map((s) => [s.id, s.narration || `${s.name}. ${speakable(s.description)}`])),
            }}
          />
          {stage && (
            <aside className="flex flex-col self-start rounded-xl border border-border bg-card" aria-live="polite">
              <div className="p-4">
                <p className="eyebrow tabular-nums">
                  {String(n + 1).padStart(2, "0")} / {String(data.stages.length).padStart(2, "0")} · {ROLE_OF[stage.type]}
                </p>
                <h3 className="mt-1 text-[17px] font-semibold">{stage.name}</h3>
                <Markdown text={stage.description} className="mt-2 text-[13px] text-muted-foreground" />
                {(into.length > 0 || out.length > 0) && (
                  <dl className="mt-3 space-y-1 text-[12px]">
                    {into.length > 0 && (
                      <div className="flex gap-2">
                        <dt className="w-10 shrink-0 text-muted-foreground">from</dt>
                        <dd>{into.map((l) => name(l.from) + (l.label ? ` (${l.label})` : "")).join(", ")}</dd>
                      </div>
                    )}
                    {out.length > 0 && (
                      <div className="flex gap-2">
                        <dt className="w-10 shrink-0 text-muted-foreground">to</dt>
                        <dd>
                          {out.map((l) => (l.loop ? "↺ " : "") + name(l.to) + (l.label ? ` (${l.label})` : "")).join(", ")}
                        </dd>
                      </div>
                    )}
                  </dl>
                )}
              </div>
              <div className="border-t border-border py-1">
                <CitationChip file={stage.cite.file} start={stage.cite.start_line} end={stage.cite.end_line} variant="row" />
              </div>
              <div className="mt-auto flex gap-2 border-t border-border p-3">
                <Button size="sm" variant="outline" className="flex-1" onClick={() => setSelected(data.stages[Math.max(0, n - 1)].id)} disabled={n <= 0}>
                  ← Prev
                </Button>
                <Button size="sm" variant="outline" className="flex-1" onClick={() => setSelected(data.stages[Math.min(data.stages.length - 1, n + 1)].id)} disabled={n >= data.stages.length - 1}>
                  Next →
                </Button>
                <Button size="sm" onClick={() => onAsk(`In the pipeline, how does the "${stage.name}" stage work, and what does it pass to the next stage?`)}>
                  <MessageSquare className="size-3.5" /> Ask
                </Button>
              </div>
            </aside>
          )}
        </FadeIn>

        <FadeIn delay={0.1}>
          <SectionLabel>Parts</SectionLabel>
          <ul className="flex flex-wrap gap-x-5 gap-y-1.5 text-[13px] text-muted-foreground">
            {types.map((t) => (
              <li key={t}>
                <span className="font-medium text-foreground">{PART_OF[t]}</span> = {ROLE_OF[t].toLowerCase()}
              </li>
            ))}
            <li><span className="font-medium text-foreground">Pipe</span> = hand-off</li>
            {data.links.some((l) => l.loop) && <li><span className="font-medium text-foreground">Dashed back pipe</span> = loop</li>}
          </ul>
        </FadeIn>
      </div>
    </div>
  );
}
