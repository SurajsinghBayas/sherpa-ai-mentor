"use client";

import { useState } from "react";
import { ArrowRight, Map, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError, type Overview } from "../../lib/api";
import { CitationChip } from "../code-viewer";
import { Markdown } from "../markdown";
import { MermaidDiagram } from "../mermaid-diagram";
import { Button } from "../ui/primitives";
import { cn } from "../../lib/utils";
import { EmptyState, FadeIn, ModeBadge, SectionLabel, VerifiedBadge } from "./shared";

/* the layer is marked with a small square in a brand colour, next to its name */
const LAYER_DOT: Record<string, string> = {
  frontend: "bg-primary",
  backend: "bg-navy dark:bg-sky-brand",
  api: "bg-primary/45 dark:bg-sky-brand",
  data: "bg-tan",
  infra: "bg-bark",
};

const LAYER_LABEL: Record<string, string> = { api: "API", ui: "UI" };

function uniqueFiles<T extends { file: string }>(files: T[]): T[] {
  const seen = new Set<string>();
  return files.filter((f) => !seen.has(f.file) && seen.add(f.file));
}

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
      <div className="scroll-thin flex-1 overflow-y-auto p-6">
        <EmptyState
          busy={busy === "overview"}
          pose="analyzing"
          title="Architecture map"
          body="Sherpa resolves the real import graph, groups files into components, and explains how they connect. Every claim links to the code."
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
    <div className="scroll-thin flex-1 overflow-y-auto">
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
          <p className="mt-1.5 text-[13px] tabular-nums text-muted-foreground">
            {data.stats.files} files · {data.components.length} components · {data.stats.imports} resolved imports
            {data.stats.languages.length > 0 && <> · {data.stats.languages.slice(0, 5).join(", ")}</>}
          </p>
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
              <article key={c.key} className="flex flex-col overflow-hidden rounded-lg border border-border bg-card">
                <div className="p-4">
                  <div className="flex items-baseline justify-between gap-3">
                    <h4 className="min-w-0 truncate text-[15px] font-semibold">{c.name}</h4>
                    <span className="flex shrink-0 items-center gap-1.5 text-xs text-muted-foreground">
                      <span aria-hidden className={cn("size-2", LAYER_DOT[c.layer] || "bg-muted-foreground/40")} />
                      {LAYER_LABEL[c.layer] ?? c.layer.charAt(0).toUpperCase() + c.layer.slice(1)}
                    </span>
                  </div>
                  <p className="mt-0.5 truncate font-mono text-[11px] text-muted-foreground">
                    {c.key === "(root)" ? "repository root" : `${c.key}/`} · {c.files_count} file{c.files_count === 1 ? "" : "s"}
                  </p>
                  <Markdown text={c.description} className="mt-3 text-[13px] text-muted-foreground" />
                </div>
                {c.key_files.length > 0 && (
                  <div className="mt-auto border-t border-border py-1">
                    {uniqueFiles(c.key_files).map((f) => (
                      <CitationChip key={f.file} file={f.file} start={f.start_line} end={f.end_line} variant="row" />
                    ))}
                  </div>
                )}
              </article>
            ))}
          </div>
        </FadeIn>

        <div className="grid gap-6 lg:grid-cols-2">
          {data.flows.length > 0 && (
            <FadeIn delay={0.15}>
              <SectionLabel>Key flows to trace</SectionLabel>
              <div className="space-y-2">
                {data.flows.map((f) => (
                  <div key={f.name} className="rounded-lg border border-border bg-card p-4">
                    <div className="flex items-center gap-2">
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
            <div className="overflow-hidden rounded-lg border border-border bg-card">
              {uniqueFiles(data.start_here).map((s, i) => (
                <div key={s.file} className={cn("py-1.5", i > 0 && "border-t border-border")}>
                  <CitationChip file={s.file} start={s.start_line} end={s.end_line} variant="row" />
                  {s.why && <p className="px-3 pb-1.5 pl-[2.125rem] text-[13px] text-muted-foreground">{s.why}</p>}
                </div>
              ))}
            </div>
            {data.entrypoints.length > 0 && (
              <>
                <SectionLabel className="mt-5">Entry points</SectionLabel>
                <div className="overflow-hidden rounded-lg border border-border bg-card py-1">
                  {uniqueFiles(data.entrypoints).map((e) => (
                    <CitationChip key={e.file} file={e.file} start={e.line} end={e.line + 10} variant="row" />
                  ))}
                </div>
              </>
            )}
          </FadeIn>
        </div>
      </div>
    </div>
  );
}
