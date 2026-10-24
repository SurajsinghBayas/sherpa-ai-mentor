"use client";

import { useEffect, useMemo, useState } from "react";
import { ChevronRight, FolderGit2, FolderTree, Layers, MessageSquare, RefreshCw, Search, Server, X } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError, type Stack, type StackGroup, type StackItem } from "../../lib/api";
import { CitationChip } from "../code-viewer";
import { Badge, Button, Input } from "../ui/primitives";
import { cn } from "../../lib/utils";
import { EmptyState, FadeIn, SectionLabel } from "./shared";

// language bar: brand tokens, biggest share first; the rest share the last swatch
const SWATCH = ["bg-primary", "bg-tan", "bg-sky-brand", "bg-success", "bg-bark", "bg-warning"];
const REST = "bg-muted-foreground/40";

function LanguageBar({ languages }: { languages: Stack["languages"] }) {
  if (!languages.length) return null;
  const top = languages.slice(0, SWATCH.length);
  const rest = languages.slice(SWATCH.length).reduce((n, l) => n + l.share, 0);
  const pct = (x: number) => `${Math.max(0.5, Math.round(x * 1000) / 10)}%`;
  return (
    <div>
      <div className="flex h-2 overflow-hidden rounded-full bg-secondary" aria-hidden>
        {top.map((l, i) => (
          <span key={l.name} className={SWATCH[i]} style={{ width: pct(l.share) }} />
        ))}
        {rest > 0 && <span className={REST} style={{ width: pct(rest) }} />}
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
        {top.map((l, i) => (
          <li key={l.name} className="flex items-center gap-1.5">
            <span className={cn("size-2 rounded-full", SWATCH[i])} />
            <span className="font-medium text-foreground">{l.name}</span>
            <span className="tabular-nums">
              {Math.round(l.share * 100)}% · {l.files} file{l.files === 1 ? "" : "s"}
            </span>
          </li>
        ))}
        {rest > 0 && (
          <li className="flex items-center gap-1.5">
            <span className={cn("size-2 rounded-full", REST)} />
            Other {Math.round(rest * 100)}%
          </li>
        )}
      </ul>
    </div>
  );
}

/** One expandable row of the tree; children hang off a guide line, like `tree` in a terminal. */
function Branch({
  open,
  onToggle,
  label,
  children,
  level,
}: {
  open: boolean;
  onToggle: () => void;
  label: React.ReactNode;
  children: React.ReactNode;
  level: number;
}) {
  return (
    <li role="treeitem" aria-expanded={open} aria-level={level} className="relative">
      <button
        type="button"
        onClick={onToggle}
        className="group flex w-full min-w-0 items-center gap-1.5 rounded-md py-1 pl-1 pr-2 text-left transition-colors hover:bg-secondary/70"
      >
        <ChevronRight
          className={cn("size-3.5 shrink-0 text-muted-foreground transition-transform duration-150", open && "rotate-90")}
        />
        {label}
      </button>
      {open && (
        <ul role="group" className="ml-[11px] border-l border-border pl-3">
          {children}
        </ul>
      )}
    </li>
  );
}

function Leaf({ item, onAsk }: { item: StackItem; onAsk: (q: string) => void }) {
  // the package(s) behind a friendly name: "@remotion/cli, remotion"
  const pkgs = [item.package, ...(item.also ?? [])].filter(Boolean);
  const what = pkgs.length > 1 || (pkgs[0] && pkgs[0] !== item.name) ? pkgs.join(", ") : "";
  return (
    <li
      role="treeitem"
      aria-level={4}
      className="group relative flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5 rounded-md py-1 pl-1 pr-1 transition-colors before:absolute before:-left-3 before:top-1/2 before:h-px before:w-2.5 before:bg-border hover:bg-secondary/50"
    >
      <span className="text-[13px] font-medium">{item.name}</span>
      {item.version && <span className="font-mono text-[11px] text-muted-foreground">{item.version}</span>}
      {item.dev && (
        <Badge variant="outline" className="px-1 py-0 text-[10px] font-normal leading-4" title="Only a dev or test dependency">
          dev
        </Badge>
      )}
      {(what || item.detail) && (
        <span className="min-w-0 truncate text-[11px] text-muted-foreground">{[what, item.detail].filter(Boolean).join(" · ")}</span>
      )}
      <span className="ml-auto flex items-center gap-1.5">
        <CitationChip file={item.cite.file} start={item.cite.start_line} end={item.cite.end_line} variant="inline" className="text-[11px]" />
        <button
          type="button"
          onClick={() => onAsk(`How is ${item.name} used in this repo, and where is it set up?`)}
          className="rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-secondary hover:text-foreground focus-visible:opacity-100 group-hover:opacity-100 max-sm:opacity-100"
          title={`Ask Sherpa how ${item.name} is used`}
          aria-label={`Ask Sherpa how ${item.name} is used`}
        >
          <MessageSquare className="size-3.5" />
        </button>
      </span>
    </li>
  );
}

const gkey = (g: StackGroup) => `g:${g.path}`;
const ckey = (g: StackGroup, id: string) => `c:${g.path}:${id}`;

function matches(item: StackItem, q: string) {
  return [item.name, item.package, item.detail, item.version, ...(item.also ?? [])].some((s) => s?.toLowerCase().includes(q));
}

export function StackPanel({
  repoId,
  active,
  busy,
  setBusy,
  onAsk,
}: {
  repoId: string;
  active: boolean;
  busy: string | null;
  setBusy: (v: string | null) => void;
  onAsk: (q: string) => void;
}) {
  const [stack, setStack] = useState<Stack | null>(null);
  const [failed, setFailed] = useState(false);
  const [closed, setClosed] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");

  async function load(refresh = false) {
    setBusy("stack");
    setFailed(false);
    try {
      const s = await api.stack(repoId, refresh);
      setStack(s);
      // long tails of unknown packages start folded
      setClosed(new Set(s.groups.flatMap((g) => g.categories.filter((c) => c.id === "other").map((c) => ckey(g, c.id)))));
    } catch (e) {
      setFailed(true);
      toast.error(e instanceof ApiError ? e.message : "Couldn't read the tech stack");
    } finally {
      setBusy(null);
    }
  }

  // free and quick (read from manifests, no model), so it loads the first time the tab is opened
  useEffect(() => {
    if (active && repoId && !stack && !failed && !busy) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, repoId]);

  const q = query.trim().toLowerCase();
  const groups = useMemo(() => {
    if (!stack) return [];
    if (!q) return stack.groups;
    return stack.groups
      .map((g) => ({
        ...g,
        categories: g.categories
          .map((c) => ({ ...c, items: c.items.filter((i) => matches(i, q) || c.label.toLowerCase().includes(q)) }))
          .filter((c) => c.items.length),
      }))
      .filter((g) => g.categories.length);
  }, [stack, q]);

  const isOpen = (k: string) => !!q || !closed.has(k);
  const toggle = (k: string) =>
    setClosed((s) => {
      const n = new Set(s);
      n.has(k) ? n.delete(k) : n.add(k);
      return n;
    });
  const allKeys = () => (stack ? stack.groups.flatMap((g) => [gkey(g), ...g.categories.map((c) => ckey(g, c.id))]) : []);

  if (!stack) {
    return (
      <div className="scroll-thin flex-1 overflow-y-auto p-6">
        <EmptyState
          busy={busy === "stack"}
          pose="analyzing"
          title="Tech stack"
          body="Every framework, database, AI library, test tool and deploy config this repo uses, read from its own manifests, as a tree. Each entry links to the line that declares it."
        >
          <Button onClick={() => load()} disabled={!repoId || !!busy}>
            <FolderTree className="size-4" />
            {busy === "stack" ? "Reading manifests…" : "Show the tech stack"}
          </Button>
        </EmptyState>
      </div>
    );
  }

  const workspaces = stack.groups.filter((g) => g.path !== "*").length;

  return (
    <div className="scroll-thin flex-1 overflow-y-auto p-4 sm:p-6">
      <div className="mx-auto max-w-4xl space-y-5">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="mr-auto text-lg font-semibold">Tech stack</h2>
          <span className="text-[11px] text-muted-foreground">
            {stack.technologies} technologies · {workspaces} workspace{workspaces === 1 ? "" : "s"}
          </span>
          <Button size="sm" variant="ghost" onClick={() => load(true)} disabled={!!busy} title="Read the manifests again">
            <RefreshCw className={cn("size-3.5", busy === "stack" && "animate-spin")} /> Refresh
          </Button>
        </div>

        {stack.languages.length > 0 && (
          <FadeIn>
            <SectionLabel>Languages</SectionLabel>
            <LanguageBar languages={stack.languages} />
          </FadeIn>
        )}

        {stack.groups.length === 0 ? (
          <p className="rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
            No manifests found (package.json, requirements.txt, pyproject.toml, go.mod, Cargo.toml, Dockerfile …), so
            there is no declared stack to show.
          </p>
        ) : (
          <FadeIn delay={0.05} className="rounded-xl border border-border bg-card">
            <div className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-2">
              <div className="relative min-w-[12rem] flex-1 max-sm:basis-full">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Filter: react, postgres, pytest…"
                  aria-label="Filter the tech stack"
                  className="h-8 pl-8 pr-8 text-[13px]"
                />
                {query && (
                  <button
                    type="button"
                    onClick={() => setQuery("")}
                    className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 text-muted-foreground hover:text-foreground"
                    aria-label="Clear the filter"
                  >
                    <X className="size-3.5" />
                  </button>
                )}
              </div>
              <Button size="sm" variant="ghost" className="h-8 text-xs" onClick={() => setClosed(new Set())}>
                Expand all
              </Button>
              <Button size="sm" variant="ghost" className="h-8 text-xs" onClick={() => setClosed(new Set(allKeys()))}>
                Collapse all
              </Button>
            </div>

            <div className="overflow-x-auto p-3">
              {groups.length === 0 ? (
                <p className="px-1 py-4 text-sm text-muted-foreground">Nothing matches “{query}”.</p>
              ) : (
                <ul role="tree" aria-label={`Tech stack of ${stack.repo}`} className="min-w-[20rem]">
                  <li role="treeitem" aria-expanded aria-level={1}>
                    <div className="flex items-center gap-2 px-1 py-1">
                      <Layers className="size-4 text-primary" />
                      <span className="text-sm font-semibold">{stack.repo}</span>
                    </div>
                    <ul role="group" className="ml-[11px] border-l border-border pl-3">
                      {groups.map((g) => (
                        <Branch
                          key={g.path}
                          level={2}
                          open={isOpen(gkey(g))}
                          onToggle={() => toggle(gkey(g))}
                          label={
                            <>
                              {g.path === "*" ? (
                                <Server className="size-4 shrink-0 text-muted-foreground" />
                              ) : (
                                <FolderGit2 className="size-4 shrink-0 text-muted-foreground" />
                              )}
                              <span className={cn("truncate text-[13px] font-semibold", g.path !== "*" && "font-mono")}>{g.name}</span>
                              <span className="shrink-0 rounded-full bg-secondary px-1.5 text-[11px] tabular-nums text-muted-foreground">
                                {q ? g.categories.reduce((n, c) => n + c.items.length, 0) : g.count}
                              </span>
                              {g.manifests.length > 0 && (
                                <span className="ml-auto hidden truncate font-mono text-[11px] text-muted-foreground sm:inline">
                                  {g.manifests.map((m) => m.split("/").pop()).join(" · ")}
                                </span>
                              )}
                            </>
                          }
                        >
                          {g.categories.map((c) => (
                            <Branch
                              key={c.id}
                              level={3}
                              open={isOpen(ckey(g, c.id))}
                              onToggle={() => toggle(ckey(g, c.id))}
                              label={
                                <>
                                  <span className="text-[13px] text-muted-foreground group-hover:text-foreground">{c.label}</span>
                                  <span className="text-[11px] tabular-nums text-muted-foreground">({c.items.length})</span>
                                </>
                              }
                            >
                              {c.items.map((it) => (
                                <Leaf key={`${it.name}|${it.detail ?? ""}|${it.cite.file}`} item={it} onAsk={onAsk} />
                              ))}
                            </Branch>
                          ))}
                        </Branch>
                      ))}
                    </ul>
                  </li>
                </ul>
              )}
            </div>
          </FadeIn>
        )}
      </div>
    </div>
  );
}
