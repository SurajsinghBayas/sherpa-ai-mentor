"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  AlertCircle, BookOpen, CheckCircle2, ChevronDown, FolderGit2, ListTodo, Map, MessageSquare,
  Plus, RefreshCw, Route, Trash2,
} from "lucide-react";
import { api, ApiError, type Health, type Repo } from "../lib/api";
import { useAuth } from "../lib/auth";
import { cn } from "../lib/utils";
import { CodeViewerProvider } from "./code-viewer";
import { SherpaOrb } from "./sherpa-orb";
import { Badge, Button, Input } from "./ui/primitives";
import { AskPanel } from "./workspace/ask-panel";
import { DocsPanel } from "./workspace/docs-panel";
import { OverviewPanel } from "./workspace/overview-panel";
import { Dots, timeAgo } from "./workspace/shared";
import { TasksPanel } from "./workspace/tasks-panel";
import { TourPanel } from "./workspace/tour-panel";

type TabId = "ask" | "overview" | "tour" | "tasks" | "docs";

const NAV: { id: TabId; icon: typeof Map; label: string; short: string; hint: string }[] = [
  { id: "overview", icon: Map, label: "Architecture", short: "Map", hint: "Main parts & how they connect" },
  { id: "ask", icon: MessageSquare, label: "Ask Sherpa", short: "Ask", hint: "How / why questions, cited" },
  { id: "tour", icon: Route, label: "Code Tours", short: "Tours", hint: "Walk a flow step by step" },
  { id: "tasks", icon: ListTodo, label: "Starter Tasks", short: "Tasks", hint: "Your first contribution" },
  { id: "docs", icon: BookOpen, label: "Living Docs", short: "Docs", hint: "Onboarding guide, kept in sync" },
];

const DEMO_REPO = "https://github.com/fastapi/full-stack-fastapi-template";
const LAST_REPO_KEY = "sherpa.repo";
const RECHECK_MS = 5 * 60_000; // while the tab is open
const FOCUS_RECHECK_MS = 2 * 60_000; // when the user comes back to the tab

/** Whether the open repo matches its source: checked automatically, rebuilt on demand. */
type Freshness = {
  state: "idle" | "checking" | "reindexing" | "up_to_date" | "outdated" | "error";
  detail?: string;
};

const shortSha = (c: string) => (/^[0-9a-f]{8,}$/i.test(c) ? c.slice(0, 7) : c);

function FreshnessChip({ f }: { f: Freshness }) {
  if (f.state === "checking")
    return (
      <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground" title="Comparing with the latest commit">
        <Dots /> checking
      </span>
    );
  if (f.state === "up_to_date")
    return (
      <span className="flex items-center gap-1 text-[11px] text-muted-foreground" title="Matches the latest commit">
        <CheckCircle2 className="size-3 text-emerald-500" /> up to date
      </span>
    );
  if (f.state === "outdated" || f.state === "error")
    return (
      <span
        className={cn("flex items-center gap-1 text-[11px]", f.state === "outdated" ? "text-amber-500" : "text-muted-foreground")}
        title={f.detail}
      >
        <AlertCircle className="size-3" /> {f.state === "outdated" ? "new commits" : "couldn't check"}
      </span>
    );
  return null;
}

function RepoBar({
  repos,
  current,
  onSelect,
  onIndexed,
  onDeleted,
  localAllowed,
  freshness,
  onReindex,
}: {
  repos: Repo[];
  current: Repo | null;
  onSelect: (r: Repo) => void;
  onIndexed: (r: Repo) => void;
  onDeleted: (r: Repo) => void;
  localAllowed: boolean;
  freshness: Freshness;
  onReindex: () => void;
}) {
  const [adding, setAdding] = useState(!current);
  const [source, setSource] = useState(current ? "" : DEMO_REPO);
  const [indexing, setIndexing] = useState(false);
  const [menu, setMenu] = useState(false);

  useEffect(() => {
    // show the "index a repo" box only when there is nothing to work on yet
    setAdding(!current);
    if (current) setSource("");
  }, [current]);

  async function index() {
    const s = source.trim();
    if (!s) return;
    setIndexing(true);
    try {
      const isUrl = /^https?:\/\//.test(s);
      const r = await api.ingest(isUrl ? { repo_url: s } : { local_path: s });
      const n = (r.changes.added?.length || 0) + (r.changes.modified?.length || 0) + (r.changes.removed?.length || 0);
      toast.success(`Indexed ${r.name}: ${r.files} files${n ? ` · ${n} changed since last index` : ""}`);
      onIndexed(r);
      setAdding(false);
      setSource("");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Indexing failed");
    } finally {
      setIndexing(false);
    }
  }

  async function remove(r: Repo) {
    if (!window.confirm(`Delete ${r.name}? Its index, overview, tasks and docs are removed.`)) return;
    try {
      await api.deleteRepo(r.repo_id);
      toast.success(`Deleted ${r.name}`);
      onDeleted(r);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Delete failed");
    }
  }

  return (
    <div className="border-b border-border bg-card/60 px-4 py-2.5">
      <div className="flex items-center gap-3">
        <FolderGit2 className="size-4 shrink-0 text-muted-foreground" />
        <div className="relative min-w-0 flex-1">
          {current ? (
            <button
              onClick={() => setMenu((v) => !v)}
              className="flex max-w-full items-center gap-2 rounded-md px-1.5 py-1 hover:bg-secondary"
            >
              <span className="truncate text-sm font-medium">{current.name}</span>
              <span className="hidden truncate font-mono text-[11px] text-muted-foreground md:inline">
                {current.files} files{current.commit ? ` · ${shortSha(current.commit)}` : ""} · indexed {timeAgo(current.indexed_at)}
              </span>
              <ChevronDown className="size-3.5 shrink-0 text-muted-foreground" />
            </button>
          ) : (
            <span className="text-sm text-muted-foreground">No repository selected</span>
          )}
          {menu && (
            <div className="absolute left-0 top-full z-40 mt-1 w-[min(28rem,90vw)] rounded-xl border border-border bg-popover p-1 shadow-xl">
              {repos.map((r) => (
                <div
                  key={r.repo_id}
                  className={cn("group flex items-center rounded-lg hover:bg-secondary", r.repo_id === current?.repo_id && "bg-secondary")}
                >
                  <button
                    onClick={() => {
                      onSelect(r);
                      setMenu(false);
                    }}
                    className="flex min-w-0 flex-1 items-center gap-2 px-3 py-2 text-left text-sm"
                  >
                    <span className="min-w-0 flex-1 truncate">{r.name}</span>
                    <span className="shrink-0 text-[11px] text-muted-foreground">{r.files} files</span>
                    {r.has_docs && <BookOpen className="size-3 shrink-0 text-muted-foreground" />}
                  </button>
                  <button
                    onClick={() => remove(r)}
                    title={`Delete ${r.name}`}
                    aria-label={`Delete ${r.name}`}
                    className="mr-1 rounded-md p-1.5 text-muted-foreground opacity-60 hover:bg-destructive/15 hover:text-destructive hover:opacity-100 group-hover:opacity-100"
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </div>
              ))}
              <button
                onClick={() => {
                  setAdding(true);
                  setMenu(false);
                }}
                className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-muted-foreground hover:bg-secondary hover:text-foreground"
              >
                <Plus className="size-3.5" /> Index another repository
              </button>
            </div>
          )}
        </div>
        {current && (
          <div className="hidden shrink-0 sm:block">
            <FreshnessChip f={freshness} />
          </div>
        )}
        {current && current.kind !== "self" && (
          <Button
            size="sm"
            variant={freshness.state === "outdated" ? "outline" : "ghost"}
            onClick={onReindex}
            disabled={freshness.state === "reindexing" || freshness.state === "checking"}
            title="Rebuild the whole index from the latest code"
          >
            <RefreshCw className={cn("size-3.5", freshness.state === "reindexing" && "animate-spin")} />
            <span className="hidden md:inline">{freshness.state === "reindexing" ? "Reindexing…" : "Reindex"}</span>
          </Button>
        )}
        {current && !adding && (
          <Button size="sm" variant="ghost" onClick={() => setAdding(true)}>
            <Plus className="size-3.5" /> <span className="hidden md:inline">Add repo</span>
          </Button>
        )}
      </div>
      {adding && (
        <div className="mt-2.5 flex gap-2">
          <Input
            value={source}
            onChange={(e) => setSource(e.target.value)}
            placeholder={localAllowed ? "https://github.com/org/repo  or  /path/to/local/folder" : "https://github.com/org/repo"}
            className="flex-1 font-mono text-xs"
            onKeyDown={(e) => e.key === "Enter" && !indexing && index()}
            autoFocus
          />
          <Button onClick={index} disabled={indexing || !source.trim()} size="sm" className="h-9 shrink-0">
            {indexing ? (
              <span className="flex items-center gap-1.5" title="The first index embeds every chunk — about a minute for a mid-size repo">
                <Dots /> Indexing
              </span>
            ) : (
              "Index repo"
            )}
          </Button>
          {current && (
            <Button variant="ghost" size="sm" className="h-9" onClick={() => setAdding(false)}>
              Cancel
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

export function Dashboard() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [repos, setRepos] = useState<Repo[]>([]);
  const [current, setCurrent] = useState<Repo | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [tab, setTab] = useState<TabId>("overview");
  const [busy, setBusy] = useState<string | null>(null);
  const [askSeed, setAskSeed] = useState("");
  const [tourSeed, setTourSeed] = useState("");
  const [freshness, setFreshness] = useState<Freshness>({ state: "idle" });
  const [indexRev, setIndexRev] = useState(0); // bumps when the index changes → map & tasks reload
  const currentRef = useRef<Repo | null>(null);
  const lastCheck = useRef<{ id: string; at: number } | null>(null);
  const inFlight = useRef(false);
  currentRef.current = current;

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  const loadRepos = useCallback(async (selectId?: string) => {
    try {
      const { repos } = await api.repos();
      setRepos(repos);
      let want = selectId;
      try {
        want = want || localStorage.getItem(LAST_REPO_KEY) || undefined;
      } catch {
        /* storage unavailable — fine */
      }
      setCurrent((cur) => repos.find((r) => r.repo_id === want) || (cur && repos.find((r) => r.repo_id === cur.repo_id)) || repos[0] || null);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Couldn't load repositories");
    }
  }, []);

  useEffect(() => {
    if (!user) return;
    loadRepos();
    api.health().then(setHealth).catch(() => setHealth(null));
  }, [user, loadRepos]);

  /** Automatic re-index: the server compares commits and re-indexes only changed files. */
  const checkForUpdates = useCallback(
    async (repo: Repo) => {
      if (inFlight.current || repo.kind === "self") return;
      inFlight.current = true;
      lastCheck.current = { id: repo.repo_id, at: Date.now() };
      setFreshness({ state: "checking" });
      const stillOpen = () => currentRef.current?.repo_id === repo.repo_id;
      try {
        const r = await api.checkUpdates(repo.repo_id);
        if (!stillOpen()) return;
        if (r.status === "updated") {
          const n = r.changed_count;
          toast.success(
            `${repo.name} has new commits (${shortSha(r.previous_commit) || "?"} → ${shortSha(r.commit)}): re-indexed ${n} changed file${n === 1 ? "" : "s"}`
          );
          if (n) setIndexRev((v) => v + 1);
          loadRepos(repo.repo_id);
          setFreshness({ state: "up_to_date" });
        } else if (r.status === "up_to_date") {
          setFreshness({ state: "up_to_date" });
        } else if (r.status === "outdated" || r.status === "error") {
          setFreshness({ state: r.status, detail: r.detail });
        } else {
          setFreshness({ state: "idle" });
        }
      } catch (e) {
        if (stillOpen()) setFreshness({ state: "error", detail: e instanceof ApiError ? e.message : "check failed" });
      } finally {
        inFlight.current = false;
      }
    },
    [loadRepos]
  );

  // check when a repo is opened …
  useEffect(() => {
    if (current) checkForUpdates(current);
    else setFreshness({ state: "idle" });
    // only when the selected repo changes, not when its summary refreshes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current?.repo_id, checkForUpdates]);

  // … when the user returns to the tab, and periodically while it stays open
  useEffect(() => {
    const due = (ms: number) => {
      const r = currentRef.current;
      if (!r || document.visibilityState !== "visible") return;
      const last = lastCheck.current;
      if (!last || last.id !== r.repo_id || Date.now() - last.at > ms) checkForUpdates(r);
    };
    const onFocus = () => due(FOCUS_RECHECK_MS);
    const timer = window.setInterval(() => due(RECHECK_MS), 60_000);
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onFocus);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onFocus);
    };
  }, [checkForUpdates]);

  /** Manual re-index: rebuild everything from the latest code. */
  async function reindex() {
    const repo = currentRef.current;
    if (!repo || inFlight.current) return;
    inFlight.current = true;
    setFreshness({ state: "reindexing" });
    try {
      const r = await api.reindex(repo.repo_id);
      toast.success(`Reindexed ${r.name}: ${r.files} files · ${r.chunks} chunks${r.commit ? ` at ${shortSha(r.commit)}` : ""}`);
      setIndexRev((v) => v + 1);
      lastCheck.current = { id: repo.repo_id, at: Date.now() };
      loadRepos(repo.repo_id);
      setFreshness({ state: "up_to_date" });
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Reindex failed");
      setFreshness({ state: "error", detail: e instanceof ApiError ? e.message : "reindex failed" });
    } finally {
      inFlight.current = false;
    }
  }

  function select(r: Repo) {
    setCurrent(r);
    try {
      localStorage.setItem(LAST_REPO_KEY, r.repo_id);
    } catch {
      /* ignore */
    }
  }

  const askAbout = useCallback((q: string) => {
    setAskSeed(q);
    setTab("ask");
  }, []);
  const tourFlow = useCallback((f: string) => {
    setTourSeed(f);
    setTab("tour");
  }, []);
  const clearAsk = useCallback(() => setAskSeed(""), []);
  const clearTour = useCallback(() => setTourSeed(""), []);

  if (loading || !user) {
    return (
      <main className="flex h-[calc(100vh-3.5rem)] items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <SherpaOrb size="lg" state="thinking" />
          <p className="text-sm text-muted-foreground">Loading your workspace…</p>
        </div>
      </main>
    );
  }

  const repoId = current?.repo_id || "";
  return (
    <CodeViewerProvider repoId={repoId}>
      <div className="flex h-[calc(100vh-3.5rem)]">
        <aside className="hidden w-60 shrink-0 flex-col border-r border-border bg-card/40 sm:flex">
          <div className="flex items-center gap-3 border-b border-border px-4 py-5">
            <SherpaOrb size="sm" state={busy ? "thinking" : "idle"} />
            <div>
              <p className="text-sm font-semibold">Sherpa</p>
              <p className="text-[10px] text-muted-foreground">AI codebase mentor</p>
            </div>
          </div>
          <nav className="flex-1 space-y-0.5 p-2 pt-3">
            {NAV.map(({ id, icon: Icon, label, hint }) => (
              <button
                key={id}
                onClick={() => setTab(id)}
                className={cn(
                  "flex w-full items-start gap-3 rounded-lg px-3 py-2 text-left transition-colors duration-150",
                  tab === id ? "bg-secondary text-foreground" : "text-muted-foreground hover:bg-secondary/50 hover:text-foreground"
                )}
              >
                <Icon className="mt-0.5 size-4 shrink-0" />
                <span>
                  <span className="block text-sm font-medium">{label}</span>
                  <span className="block text-[10px] text-muted-foreground">{hint}</span>
                </span>
              </button>
            ))}
          </nav>
          {health && (
            <div className="border-t border-border p-3 text-[10px] text-muted-foreground">
              {health.llm.available ? (
                <Badge variant="secondary" className="w-full justify-center font-normal" title={`Fallbacks: ${health.llm.fallbacks.join(", ")}`}>
                  model: {health.llm.model.replace(/^[a-z0-9-]+\./i, "")}
                </Badge>
              ) : (
                <Badge variant="warning" className="w-full justify-center">offline mode — no LLM key</Badge>
              )}
            </div>
          )}
          <div className="border-t border-border px-3 py-3">
            <div className="flex items-center gap-2.5 px-1">
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-secondary text-xs font-medium uppercase">
                {(user.name || user.email).slice(0, 1)}
              </div>
              <p className="min-w-0 truncate text-xs font-medium">{user.name || user.email}</p>
            </div>
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
          <RepoBar
            repos={repos}
            current={current}
            onSelect={select}
            onIndexed={(r) => {
              select(r);
              loadRepos(r.repo_id);
            }}
            onDeleted={(r) => {
              if (r.repo_id === current?.repo_id) setCurrent(null);
              loadRepos();
            }}
            localAllowed={!!health?.local_ingest}
            freshness={freshness}
            onReindex={reindex}
          />

          <div className="flex border-b border-border bg-card/40 px-1 sm:hidden">
            {NAV.map(({ id, icon: Icon, short }) => (
              <button
                key={id}
                onClick={() => setTab(id)}
                className={cn(
                  "flex flex-1 flex-col items-center gap-0.5 py-2 text-[10px] font-medium",
                  tab === id ? "text-foreground" : "text-muted-foreground"
                )}
              >
                <Icon className="size-4" />
                {short}
              </button>
            ))}
          </div>

          {/* every panel stays mounted so results survive tab switches; keyed by repo so they reset on switch,
              and the map and tasks also reload when the index changes (the chat and tours keep their history) */}
          {(["overview", "ask", "tour", "tasks", "docs"] as TabId[]).map((id) => (
            <div key={`${id}-${repoId}${id === "overview" || id === "tasks" ? `-${indexRev}` : ""}`} className={cn("flex min-h-0 flex-1 flex-col", tab !== id && "hidden")}>
              {id === "ask" && <AskPanel repoId={repoId} repoName={current?.name || ""} seed={askSeed} onSeedUsed={clearAsk} />}
              {id === "overview" && <OverviewPanel repoId={repoId} busy={busy} setBusy={setBusy} onTour={tourFlow} />}
              {id === "tour" && (
                <TourPanel repoId={repoId} busy={busy} setBusy={setBusy} seed={tourSeed} onSeedUsed={clearTour} onAsk={askAbout} />
              )}
              {id === "tasks" && <TasksPanel repoId={repoId} busy={busy} setBusy={setBusy} onAsk={askAbout} />}
              {id === "docs" && (
                <DocsPanel
                  repoId={repoId}
                  repoName={current?.name || "repo"}
                  busy={busy}
                  setBusy={setBusy}
                  onSynced={() => loadRepos(repoId)}
                />
              )}
            </div>
          ))}
        </div>
      </div>
    </CodeViewerProvider>
  );
}
