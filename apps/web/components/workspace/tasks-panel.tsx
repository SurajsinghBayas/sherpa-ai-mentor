"use client";

import { useState } from "react";
import { Clock, GraduationCap, ListTodo, MessageSquare, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError, type Tasks } from "../../lib/api";
import { CitationChip } from "../code-viewer";
import { Markdown } from "../markdown";
import { Badge, Button } from "../ui/primitives";
import { cn } from "../../lib/utils";
import { EmptyState, FadeIn, ModeBadge } from "./shared";

export function TasksPanel({
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
  const [data, setData] = useState<Tasks | null>(null);

  async function suggest(refresh = false) {
    setBusy("tasks");
    try {
      setData(await api.tasks(repoId, refresh));
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed to suggest tasks");
    } finally {
      setBusy(null);
    }
  }

  if (!data) {
    return (
      <div className="scroll-thin flex-1 overflow-y-auto p-6">
        <EmptyState
          busy={busy === "tasks"}
          pose="coding"
          title="Starter tasks"
          body="Sherpa scans for TODOs, untested modules and refactor candidates, then turns the best ones into first-PR tasks with steps and exact files."
        >
          <Button onClick={() => suggest()} disabled={!repoId || !!busy}>
            <ListTodo className="size-4" />
            {busy === "tasks" ? "Scouting the repo…" : "Suggest tasks"}
          </Button>
        </EmptyState>
      </div>
    );
  }

  return (
    <div className="scroll-thin flex-1 overflow-y-auto p-4 sm:p-6">
      <div className="mx-auto max-w-4xl space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="mr-auto text-lg font-semibold">Good first contributions</h2>
          <span className="text-[11px] text-muted-foreground">{data.signals_found} code signals scanned</span>
          <ModeBadge mode={data.mode} model={data.model} />
          <Button size="sm" variant="ghost" onClick={() => suggest(true)} disabled={!!busy}>
            <RefreshCw className={cn("size-3.5", busy === "tasks" && "animate-spin")} /> New ideas
          </Button>
        </div>
        {data.tasks.map((t, i) => (
          <FadeIn key={i} delay={i * 0.06}>
            <div className="rounded-xl border border-border bg-card p-5">
              <div className="flex flex-wrap items-start gap-2">
                <p className="mr-auto text-[15px] font-medium">{t.title}</p>
                <Badge variant={t.difficulty === "easy" ? "success" : "info"} >
                  {t.difficulty}
                </Badge>
                {t.estimated_time && (
                  <Badge variant="outline" className="font-normal">
                    <Clock /> {t.estimated_time}
                  </Badge>
                )}
              </div>
              <Markdown text={t.why} className="mt-2 text-[13px] text-muted-foreground" />
              <div className="mt-3 flex flex-wrap gap-1">
                {t.files.map((f, j) => (
                  <CitationChip key={j} file={f.file} start={f.start_line} end={f.end_line} />
                ))}
              </div>
              <ol className="mt-4 space-y-2">
                {t.steps.map((s, j) => (
                  <li key={j} className="flex items-start gap-2.5 text-[13px]">
                    <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-secondary text-[11px] font-medium tabular-nums">
                      {j + 1}
                    </span>
                    <Markdown text={s} className="min-w-0 flex-1 text-[13px]" />
                  </li>
                ))}
              </ol>
              <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-border pt-3">
                {t.skills.length > 0 && (
                  <span className="mr-auto inline-flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
                    <GraduationCap className="size-3.5" />
                    {t.skills.join(" · ")}
                  </span>
                )}
                <Button
                  size="sm"
                  variant="outline"
                  className="ml-auto"
                  onClick={() => onAsk(`I want to work on: "${t.title}". What do I need to understand first, and how do I test my change?`)}
                >
                  <MessageSquare className="size-3.5" /> Ask Sherpa about this
                </Button>
              </div>
            </div>
          </FadeIn>
        ))}
      </div>
    </div>
  );
}
