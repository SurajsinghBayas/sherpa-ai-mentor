"use client";

import { useEffect, useState } from "react";
import { BookOpen, CheckCircle2, Download, GitCompare, History, RefreshCw, TriangleAlert } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError, type Docs, type SyncResult } from "../../lib/api";
import { Markdown } from "../markdown";
import { Badge, Button } from "../ui/primitives";
import { cn } from "../../lib/utils";
import { EmptyState, FadeIn, ModeBadge, SectionLabel, timeAgo } from "./shared";

export function DocsPanel({
  repoId,
  repoName,
  busy,
  setBusy,
  onSynced,
}: {
  repoId: string;
  repoName: string;
  busy: string | null;
  setBusy: (v: string | null) => void;
  onSynced: () => void;
}) {
  const [doc, setDoc] = useState<Docs | null>(null);
  const [lastSync, setLastSync] = useState<SyncResult | null>(null);
  const [showPrev, setShowPrev] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (!repoId) return;
    api.docs(repoId).then(setDoc).catch(() => setDoc(null));
  }, [repoId]);

  async function run(kind: "generate" | "refresh" | "sync") {
    setBusy("docs");
    try {
      if (kind === "generate") setDoc(await api.generateDocs(repoId));
      if (kind === "refresh") setDoc(await api.refreshDocs(repoId));
      if (kind === "sync") {
        const r = await api.sync(repoId);
        setLastSync(r);
        if (r.docs) setDoc(r.docs);
        onSynced();
        toast.success(
          r.changed_count
            ? `${r.changed_count} file(s) changed · ${r.docs_refreshed.length} doc section(s) updated`
            : "No code changes since the last index"
        );
      }
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Docs request failed");
    } finally {
      setBusy(null);
    }
  }

  async function download() {
    try {
      const md = await api.docsMarkdown(repoId);
      const url = URL.createObjectURL(new Blob([md], { type: "text/markdown" }));
      const a = Object.assign(document.createElement("a"), {
        href: url,
        download: `ONBOARDING-${repoName.replace(/[^a-z0-9]+/gi, "-")}.md`,
      });
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Download failed");
    }
  }

  if (!doc) {
    return (
      <div className="scroll-thin flex-1 overflow-y-auto p-6">
        <EmptyState
          busy={busy === "docs"}
          pose="explaining"
          title="Living onboarding docs"
          body="Generate an onboarding guide from the code. Each section remembers which files it cites, so when the code changes Sherpa flags and rewrites only the sections that went stale."
        >
          <Button onClick={() => run("generate")} disabled={!repoId || !!busy}>
            <BookOpen className="size-4" />
            {busy === "docs" ? "Writing the guide… (~20s)" : "Generate onboarding guide"}
          </Button>
        </EmptyState>
      </div>
    );
  }

  const ch = lastSync?.changes;
  return (
    <div className="scroll-thin flex-1 overflow-y-auto p-4 sm:p-6">
      <div className="mx-auto max-w-4xl space-y-6">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="mr-auto text-lg font-semibold">Onboarding guide</h2>
          {doc.fresh ? (
            <Badge variant="success">
              <CheckCircle2 /> in sync with code
            </Badge>
          ) : (
            <Badge variant="warning">
              <TriangleAlert /> {doc.stale_count} stale section{doc.stale_count === 1 ? "" : "s"}
            </Badge>
          )}
          <Button size="sm" variant="outline" onClick={() => run("sync")} disabled={!!busy} title="Re-index from the source and update stale sections">
            <GitCompare className={cn("size-3.5", busy === "docs" && "animate-pulse")} /> Sync with code
          </Button>
          {!doc.fresh && (
            <Button size="sm" onClick={() => run("refresh")} disabled={!!busy}>
              <RefreshCw className="size-3.5" /> Update stale
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={download} title="Download as Markdown">
            <Download className="size-3.5" />
          </Button>
        </div>

        {ch && (
          <FadeIn>
            <div className="rounded-xl border border-border bg-card p-4 text-[13px]">
              <p className="font-medium">Last sync</p>
              {lastSync!.changed_count === 0 ? (
                <p className="mt-1 text-muted-foreground">No files changed since the previous index.</p>
              ) : (
                <div className="mt-2 grid gap-2 sm:grid-cols-3">
                  {(["modified", "added", "removed"] as const).map((k) => (
                    <div key={k}>
                      <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
                        {k} ({ch[k]?.length || 0})
                      </p>
                      {(ch[k] || []).slice(0, 6).map((f) => (
                        <p key={f} className="truncate font-mono text-[11px]">{f}</p>
                      ))}
                    </div>
                  ))}
                </div>
              )}
              {lastSync!.docs_refreshed.length > 0 && (
                <p className="mt-2 text-success">
                  Rewrote: {lastSync!.docs_refreshed.join(", ")}
                </p>
              )}
            </div>
          </FadeIn>
        )}

        {doc.sections.map((s, i) => (
          <FadeIn key={s.id} delay={i * 0.04}>
            <section
              className={cn(
                "rounded-xl border bg-card p-5",
                s.stale ? "border-warning/40" : "border-border"
              )}
            >
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <h3 className="mr-auto text-base font-semibold">{s.title}</h3>
                {s.stale && (
                  <Badge variant="warning" title={s.changed_files.join("\n")}>
                    <TriangleAlert /> code changed: {s.changed_files.slice(0, 2).map((f) => f.split("/").pop()).join(", ")}
                    {s.changed_files.length > 2 ? ` +${s.changed_files.length - 2}` : ""}
                  </Badge>
                )}
                <span className="text-[11px] text-muted-foreground">updated {timeAgo(s.updated_at)}</span>
                <ModeBadge mode={s.mode} />
              </div>
              <Markdown text={s.markdown} />
              {s.previous_markdown && (
                <div className="mt-3 border-t border-border pt-2">
                  <button
                    onClick={() => setShowPrev((p) => ({ ...p, [s.id]: !p[s.id] }))}
                    className="text-[11px] text-muted-foreground hover:text-foreground"
                  >
                    {showPrev[s.id] ? "Hide" : "Show"} previous version
                  </button>
                  {showPrev[s.id] && (
                    <div className="mt-2 rounded-lg bg-secondary/40 p-3 opacity-70">
                      <Markdown text={s.previous_markdown} className="text-[12px]" />
                    </div>
                  )}
                </div>
              )}
            </section>
          </FadeIn>
        ))}

        <div>
          <SectionLabel className="flex items-center gap-1.5">
            <History className="size-3" /> Changelog
          </SectionLabel>
          <ul className="space-y-1.5 text-[12px] text-muted-foreground">
            {[...doc.changelog].reverse().map((c, i) => (
              <li key={i}>
                <span className="text-foreground">{c.event}</span> {c.sections.join(", ")} · {timeAgo(c.at)}
                {c.changed_files.length > 0 && <> · after changes to {c.changed_files.slice(0, 3).join(", ")}</>}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
