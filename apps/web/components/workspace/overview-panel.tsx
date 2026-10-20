"use client";

import { useState } from "react";
import { ArrowRight, Boxes, DoorOpen, Map, RefreshCw, Route } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError, type Overview } from "../../lib/api";
import { CitationChip } from "../code-viewer";
import { Markdown } from "../markdown";
import { MermaidDiagram } from "../mermaid-diagram";
import { Badge, Button } from "../ui/primitives";
import { cn } from "../../lib/utils";
import { EmptyState, FadeIn, ModeBadge, SectionLabel, VerifiedBadge } from "./shared";

const LAYER_TONE: Record<string, string> = {
  frontend: "border-l-violet-500/70",
  backend: "border-l-sky-500/70",
  api: "border-l-emerald-500/70",
  data: "border-l-amber-500/70",
  infra: "border-l-rose-500/70",
  tooling: "border-l-zinc-500/70",
  docs: "border-l-zinc-500/70",
  tests: "border-l-zinc-500/70",
  shared: "border-l-teal-500/70",
};

export function OverviewPanel({
  repoId,
  busy,
  setBusy,
  onTour,
}: {
  repoId: string;
  busy: string | null;
  setBusy: (v: string | null) => void;
  onTour: (flow: string) => void;
}) {
  const [data, setData] = useState<Overview | null>(null);

  async function generate(refresh = false) {
    setBusy("overview");
    try {
      setData(await api.overview(repoId, refresh));
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed to build the overview");
    } finally {
      setBusy(null);
    }
  }

  if (!data) {
    return (
      <div className="custom-scroll flex-1 overflow-y-auto p-6">
        <EmptyState
          busy={busy === "overview"}
          title="Architecture map"
          body="Sherpa resolves the real import graph, groups files into components, and explains how they connect — every claim linked to code."
        >
          <Button onClick={() => generate()} disabled={!repoId || !!busy}>
            <Map className="size-4" />
            {busy === "overview" ? "Mapping the codebase…" : "Generate overview"}
          </Button>
          {!repoId && <p className="text-xs text-muted-foreground">Index a repo first.</p>}
        </EmptyState>
      </div>
    );
  }

  return (
    <div className="custom-scroll flex-1 overflow-y-auto">
      <div className="mx-auto max-w-5xl space-y-8 p-4 sm:p-6">
        <FadeIn>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="mr-auto text-lg font-semibold">Architecture overview</h2>
            <ModeBadge mode={data.mode} model={data.model} />
            <VerifiedBadge n={data.citations.length} />
            <Button size="sm" variant="ghost" onClick={() => generate(true)} disabled={!!busy}>
              <RefreshCw className={cn("size-3.5", busy === "overview" && "animate-spin")} /> Regenerate
            </Button>
          </div>
          <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
            <Badge variant="outline" className="font-normal">{data.stats.files} files</Badge>
            <Badge variant="outline" className="font-normal">{data.components.length} components</Badge>
            <Badge variant="outline" className="font-normal">{data.stats.imports} resolved imports</Badge>
            {data.stats.languages.slice(0, 5).map((l) => (
              <Badge key={l} variant="outline" className="font-normal">{l}</Badge>
            ))}
          </div>
          <div className="mt-4 rounded-xl border border-border bg-card p-4">
            <Markdown text={data.summary} />
          </div>
        </FadeIn>

        <FadeIn delay={0.05}>
          <SectionLabel>How the parts connect</SectionLabel>
          <MermaidDiagram code={data.mermaid} />
          <p className="mt-2 text-[11px] text-muted-foreground">
            Arrows are real import relationships found by static analysis (count = number of importing files).
          </p>
        </FadeIn>

        <FadeIn delay={0.1}>
          <SectionLabel>Components</SectionLabel>
          <div className="grid gap-3 md:grid-cols-2">
            {data.components.map((c) => (
              <div
                key={c.key}
                className={cn("rounded-xl border border-l-4 border-border bg-card p-4", LAYER_TONE[c.layer] || LAYER_TONE.shared)}
              >
                <div className="flex items-start gap-2">
                  <Boxes className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <p className="font-medium">{c.name}</p>
                    <p className="truncate font-mono text-[11px] text-muted-foreground">
                      {c.key}/ · {c.files_count} file{c.files_count === 1 ? "" : "s"}
                    </p>
                  </div>
                  <Badge variant="outline" className="shrink-0 text-[10px] font-normal">{c.layer}</Badge>
                </div>
                <Markdown text={c.description} className="mt-2 text-[13px] text-muted-foreground" />
                <div className="mt-2 flex flex-wrap gap-1">
                  {c.key_files.map((f) => (
                    <CitationChip key={f.file} file={f.file} start={f.start_line} end={f.end_line} compact />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </FadeIn>

        <div className="grid gap-6 lg:grid-cols-2">
          {data.flows.length > 0 && (
            <FadeIn delay={0.15}>
              <SectionLabel>Key flows to trace</SectionLabel>
              <div className="space-y-2">
                {data.flows.map((f) => (
                  <div key={f.name} className="rounded-xl border border-border bg-card p-4">
                    <div className="flex items-center gap-2">
                      <Route className="size-4 shrink-0 text-muted-foreground" />
                      <p className="flex-1 font-medium">{f.name}</p>
                      <Button size="sm" variant="outline" onClick={() => onTour(f.name)}>
                        Tour it <ArrowRight className="size-3.5" />
                      </Button>
                    </div>
                    <Markdown text={f.description} className="mt-2 text-[13px] text-muted-foreground" />
                  </div>
                ))}
              </div>
            </FadeIn>
          )}
          <FadeIn delay={0.2}>
            <SectionLabel>Start reading here</SectionLabel>
            <div className="space-y-2">
              {data.start_here.map((s) => (
                <div key={s.file} className="rounded-xl border border-border bg-card p-4">
                  <div className="flex items-center gap-2">
                    <DoorOpen className="size-4 shrink-0 text-muted-foreground" />
                    <CitationChip file={s.file} start={s.start_line} end={s.end_line} />
                  </div>
                  {s.why && <p className="mt-1.5 text-[13px] text-muted-foreground">{s.why}</p>}
                </div>
              ))}
              {data.entrypoints.length > 0 && (
                <div className="rounded-xl border border-dashed border-border p-4">
                  <p className="mb-2 text-xs font-medium text-muted-foreground">Detected entrypoints</p>
                  <div className="flex flex-wrap gap-1">
                    {data.entrypoints.map((e) => (
                      <CitationChip key={e.file} file={e.file} start={e.line} end={e.line + 10} compact />
                    ))}
                  </div>
                </div>
              )}
            </div>
          </FadeIn>
        </div>
      </div>
    </div>
  );
}
