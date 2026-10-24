"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { useTheme } from "next-themes";
import {
  AlertCircle, BookOpen, Building2, CheckCircle2, ChevronsUpDown, Command as CommandIcon, Ellipsis, FolderGit2, ListTodo,
  Cog, GraduationCap, Layers, Lock, Map, MessageSquare, Moon, Plus, RefreshCw, Route, Search, Trash2, Upload,
} from "lucide-react";
import { api, ApiError, type Health, type Repo } from "../lib/api";
import { useAuth } from "../lib/auth";
import { cn } from "../lib/utils";
import { CodeViewerProvider } from "./code-viewer";
import { ImportSource } from "./import-source";
import { CommandPalette, type PaletteItem } from "./command-palette";
import { Sherpa } from "./sherpa";
import { Button, ConfirmDialog, Kbd, Menu, Tooltip } from "./ui/primitives";
import { AskPanel } from "./workspace/ask-panel";
import { CityPanel } from "./workspace/city-panel";
import { DocsPanel } from "./workspace/docs-panel";
import { MachinePanel } from "./workspace/machine-panel";
import { OverviewPanel } from "./workspace/overview-panel";
import { QuizPanel } from "./workspace/quiz-panel";
import { StackPanel } from "./workspace/stack-panel";
import { Dots, timeAgo, timeLeft } from "./workspace/shared";
import { TasksPanel } from "./workspace/tasks-panel";
import { TourPanel } from "./workspace/tour-panel";

type TabId = "ask" | "overview" | "stack" | "machine" | "city" | "tour" | "tasks" | "docs" | "quiz";

const NAV: { id: TabId; icon: typeof Map; label: string; short: string; hint: string }[] = [
  { id: "overview", icon: Map, label: "Architecture", short: "Map", hint: "Main parts and how they connect" },
  { id: "stack", icon: Layers, label: "Tech stack", short: "Stack", hint: "What it's built with, as a tree" },
  { id: "machine", icon: Cog, label: "Pipeline machine", short: "Machine", hint: "How the agent, ML or workflow runs" },
  { id: "city", icon: Building2, label: "Repo city", short: "City", hint: "Every file, and how it grew" },
  { id: "ask", icon: MessageSquare, label: "Ask Sherpa", short: "Ask", hint: "How and why, with sources" },
  { id: "tour", icon: Route, label: "Code tours", short: "Tours", hint: "Walk a flow step by step" },
  { id: "tasks", icon: ListTodo, label: "Starter tasks", short: "Tasks", hint: "Your first contribution" },
  { id: "docs", icon: BookOpen, label: "Living docs", short: "Docs", hint: "Onboarding guide, kept in sync" },
  { id: "quiz", icon: GraduationCap, label: "Skill check", short: "Skills", hint: "How well you know this code" },
];

const LAST_REPO_KEY = "sherpa.repo";

/** github.com/Owner/Repo.git and https://github.com/owner/repo/ are the same repository. */
function sameRepo(a: string, b: string) {
  const norm = (u: string) => u.trim().toLowerCase().replace(/^https?:\/\/(www\.)?/, "").replace(/(\.git)?\/*$/, "");
  return norm(a) === norm(b);
}
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
        <CheckCircle2 className="size-3 text-success" /> up to date
      </span>
    );
  if (f.state === "outdated" || f.state === "error")
    return (
      <span
        className={cn("flex items-center gap-1 text-[11px]", f.state === "outdated" ? "text-warning" : "text-muted-foreground")}
        title={f.detail}
      >
        <AlertCircle className="size-3" /> {f.state === "outdated" ? "new commits" : "couldn't check"}
      </span>
    );
  return null;
}

/** The repository switcher at the top of the sidebar (and of the page on phones). */
function RepoSwitcher({
  repos,
  current,
  onSelect,
  onAdd,
  className,
}: {
  repos: Repo[];
  current: Repo | null;
  onSelect: (r: Repo) => void;
  onAdd: () => void;
  className?: string;
}) {
  return (
    <Menu.Root>
      <Menu.Trigger
        className={cn(
          "flex w-full items-center gap-2.5 rounded-lg border border-border bg-card px-2.5 py-2 text-left shadow-card",
          "transition-colors duration-150 hover:bg-secondary data-[popup-open]:bg-secondary",
          className
        )}
      >
        <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-secondary text-muted-foreground">
          {current?.private ? <Lock className="size-4" /> : <FolderGit2 className="size-4" />}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13px] font-medium">{current ? current.name : "No repository"}</span>
          <span className="block truncate text-[11px] text-muted-foreground">
            {current
              ? `${current.files} files · ${current.private ? `private, ${timeLeft(current.expires_at)}` : timeAgo(current.indexed_at) || "indexed"}`
              : "Add one to begin"}
          </span>
        </span>
        <ChevronsUpDown className="size-4 shrink-0 text-muted-foreground" />
      </Menu.Trigger>
      <Menu.Popup className="w-[min(18rem,calc(100vw-2rem))]">
        {repos.length > 0 && <Menu.Label>Repositories</Menu.Label>}
        <div className="scroll-thin max-h-72 overflow-y-auto">
          {repos.map((r) => (
            <Menu.Item key={r.repo_id} onClick={() => onSelect(r)} className={cn(r.repo_id === current?.repo_id && "bg-secondary/60")}>
              {r.private ? <Lock aria-label="Private" /> : <FolderGit2 />}
              <span className="min-w-0 flex-1 truncate">{r.name}</span>
              <span className="shrink-0 text-[11px] tabular-nums text-muted-foreground">{r.files}</span>
            </Menu.Item>
          ))}
        </div>
        {repos.length > 0 && <Menu.Separator />}
        <Menu.Item onClick={onAdd}>
          <Plus /> Add a repository
        </Menu.Item>
      </Menu.Popup>
    </Menu.Root>
  );
}

/** The bar above the panels: what is open, how fresh it is, and what you can do with it. */
function RepoBar({
  current,
  freshness,
  adding,
  onAdd,
  onReindex,
  onDelete,
  onPalette,
}: {
  current: Repo | null;
  freshness: Freshness;
  adding: boolean;
  onAdd: () => void;
  onReindex: () => void;
  onDelete: () => void;
  onPalette: () => void;
}) {
  // while the add form is open, the bar is about that, not the repo behind it
  const repo = adding ? null : current;
  const canReindex = repo && repo.kind !== "self" && repo.kind !== "upload" && !repo.private;
  return (
    <div className="flex h-12 shrink-0 items-center gap-3 border-b border-border bg-background px-4">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        {repo ? (
          <>
            <h1 className="hidden truncate text-sm font-semibold sm:block">{repo.name}</h1>
            <span className="hidden truncate font-mono text-[11px] text-muted-foreground md:inline">
              {repo.commit ? shortSha(repo.commit) : repo.kind}
            </span>
            {repo.private ? (
              <Tooltip
                side="bottom"
                content="Code is held in server memory only and never saved. It's wiped when this expires, when you delete it, or if the server restarts."
              >
                <span className="flex shrink-0 items-center gap-1.5 rounded-full border border-border bg-secondary px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                  <Lock className="size-3" /> Private · {timeLeft(repo.expires_at)}
                </span>
              </Tooltip>
            ) : (
              <span className="hidden sm:block">
                <FreshnessChip f={freshness} />
              </span>
            )}
          </>
        ) : (
          <h1 className="text-sm font-semibold">Add a repository</h1>
        )}
      </div>

      <Tooltip content={<span className="flex items-center gap-1.5">Command menu <Kbd className="border-white/20 bg-transparent text-inherit">⌘K</Kbd></span>} side="bottom">
        <Button variant="outline" size="sm" onClick={onPalette} aria-label="Open the command menu" className="hidden gap-2 text-muted-foreground md:inline-flex">
          <Search className="size-3.5" /> Search <Kbd>⌘K</Kbd>
        </Button>
      </Tooltip>

      {repo && repo.kind === "upload" && (
        <Button size="sm" variant="outline" onClick={onAdd} title="Upload a new version; only changed files are re-indexed">
          <Upload className="size-3.5" /> <span className="hidden lg:inline">Upload new version</span>
        </Button>
      )}
      {canReindex && (
        <Button
          size="sm"
          variant="outline"
          onClick={onReindex}
          disabled={freshness.state === "reindexing" || freshness.state === "checking"}
          title="Rebuild the whole index from the latest code"
          className={cn(freshness.state === "outdated" && "border-warning/40 text-warning")}
        >
          <RefreshCw className={cn("size-3.5", freshness.state === "reindexing" && "animate-spin")} />
          <span className="hidden lg:inline">{freshness.state === "reindexing" ? "Reindexing…" : "Reindex"}</span>
        </Button>
      )}
      {repo && (
        <Menu.Root>
          <Menu.Trigger
            aria-label="More actions"
            className="flex size-8 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground data-[popup-open]:bg-secondary"
          >
            <Ellipsis className="size-4" />
          </Menu.Trigger>
          <Menu.Popup align="end" className="w-56">
            <Menu.Item onClick={onAdd}>
              <Plus /> Add a repository
            </Menu.Item>
            <Menu.Separator />
            <Menu.Item onClick={onDelete} className="text-destructive [&_svg]:text-destructive">
              <Trash2 /> Delete {repo.name}
            </Menu.Item>
          </Menu.Popup>
        </Menu.Root>
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
  const [tab, showTab] = useState<TabId>("overview");
  const [busy, setBusy] = useState<string | null>(null);
  const [askSeed, setAskSeed] = useState("");
  const [tourSeed, setTourSeed] = useState("");
  const [freshness, setFreshness] = useState<Freshness>({ state: "idle" });
  const [indexRev, setIndexRev] = useState(0); // bumps when the index changes → map & tasks reload
  const [adding, setAdding] = useState(false);
  // picking a page leaves "Add a repository" (it covers the panels while open), once there is a repo to show
  const setTab = useCallback(
    (id: TabId) => {
      showTab(id);
      if (currentRef.current) setAdding(false);
    },
    [] // eslint-disable-line react-hooks/exhaustive-deps
  );
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [palette, setPalette] = useState(false);
  const { resolvedTheme, setTheme } = useTheme();
  const currentRef = useRef<Repo | null>(null);
  const lastCheck = useRef<{ id: string; at: number } | null>(null);
  const inFlight = useRef(false);
  currentRef.current = current;

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  // ?repo=<url> (the Chrome extension opens the repo on screen): select it if indexed, else offer to index it
  const deepLink = useRef<string | null>(null);
  const [importUrl, setImportUrl] = useState<string | undefined>();
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const repo = params.get("repo");
    if (!repo || !/^https:\/\/(github\.com|gitlab\.com|bitbucket\.org)\//.test(repo)) return;
    deepLink.current = repo;
    params.delete("repo");
    window.history.replaceState(null, "", window.location.pathname + (params.size ? `?${params}` : ""));
  }, []);

  const loadRepos = useCallback(async (selectId?: string) => {
    try {
      const { repos } = await api.repos();
      setRepos(repos);
      const link = deepLink.current;
      if (link && !selectId) {
        deepLink.current = null;
        const match = repos.find((r) => sameRepo(r.source, link));
        if (match) {
          selectId = match.repo_id;
          try {
            localStorage.setItem(LAST_REPO_KEY, match.repo_id);
          } catch {
            /* storage unavailable — fine */
          }
        } else {
          setImportUrl(link);
          setAdding(true);
        }
      }
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

  useEffect(() => {
    // show the importer only when there is nothing to work on yet, or a repo is waiting to be indexed
    setAdding(!current || importUrl !== undefined);
  }, [current?.repo_id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!user) return;
    // an upload still indexing (reload, other tab, CLI): reopen the importer to show it
    api.uploads()
      .then(({ uploads }) => uploads.some((u) => u.status === "queued" || u.status === "processing") && setAdding(true))
      .catch(() => {});
  }, [user]);

  async function removeCurrent() {
    const r = currentRef.current;
    if (!r) return;
    try {
      await api.deleteRepo(r.repo_id);
      toast.success(`Deleted ${r.name}`);
      setCurrent(null);
      loadRepos();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Delete failed");
    }
  }

  /** Automatic re-index: the server compares commits and re-indexes only changed files. */
  const checkForUpdates = useCallback(
    async (repo: Repo) => {
      if (inFlight.current || repo.kind === "self" || repo.private) return;
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

  // a private repo: keep its countdown current, and when it expires say so and drop it
  const [, setTick] = useState(0);
  useEffect(() => {
    if (!current?.private || !current.expires_at) return;
    const { name, expires_at } = current;
    const t = window.setInterval(() => {
      if (Date.now() / 1000 < expires_at) return setTick((n) => n + 1);
      window.clearInterval(t);
      toast.info(`The private session for ${name} ended, and its code was wiped from memory.`);
      loadRepos();
    }, 30_000);
    return () => window.clearInterval(t);
  }, [current?.repo_id, current?.private, current?.expires_at, current?.name, loadRepos]); // eslint-disable-line react-hooks/exhaustive-deps

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
      <main className="flex h-[calc(100dvh_-_var(--header-h))] items-center justify-center">
        <div className="flex flex-col items-center gap-3" role="status">
          <Sherpa pose="walking" size={80} decorative />
          <p className="text-sm text-muted-foreground">Loading your workspace…</p>
        </div>
      </main>
    );
  }

  const repoId = current?.repo_id || "";
  const model = health?.llm.available ? health.llm.model.replace(/^[a-z0-9-]+\./i, "") : null;

  const paletteItems: PaletteItem[] = [
    ...NAV.map(({ id, icon: Icon, label, hint }) => ({
      id: `tab-${id}`,
      group: "Go to",
      label,
      hint,
      icon: <Icon />,
      run: () => setTab(id),
    })),
    ...repos.map((r) => ({
      id: `repo-${r.repo_id}`,
      group: "Repositories",
      label: r.name,
      hint: r.repo_id === repoId ? "open" : `${r.files} files`,
      icon: <FolderGit2 />,
      run: () => select(r),
    })),
    { id: "add", group: "Actions", label: "Add a repository", icon: <Plus />, run: () => setAdding(true) },
    ...(current && current.kind !== "self" && current.kind !== "upload" && !current.private
      ? [{ id: "reindex", group: "Actions", label: `Reindex ${current.name}`, icon: <RefreshCw />, run: reindex }]
      : []),
    {
      id: "theme",
      group: "Actions",
      label: resolvedTheme === "dark" ? "Switch to light theme" : "Switch to dark theme",
      icon: <Moon />,
      run: () => setTheme(resolvedTheme === "dark" ? "light" : "dark"),
    },
  ];

  return (
    <CodeViewerProvider repoId={repoId}>
      <div className="flex h-[calc(100dvh_-_var(--header-h))]">
        <aside className="hidden w-64 shrink-0 flex-col border-r border-border bg-card sm:flex">
          <div className="p-3">
            <RepoSwitcher repos={repos} current={current} onSelect={select} onAdd={() => setAdding(true)} />
          </div>
          <nav aria-label="Workspace" className="flex-1 space-y-0.5 px-3 py-1">
            {NAV.map(({ id, icon: Icon, label, hint }) => {
              const on = tab === id && !adding;
              return (
              <button
                key={id}
                onClick={() => setTab(id)}
                aria-current={on ? "page" : undefined}
                className={cn(
                  "group flex w-full items-start gap-3 rounded-lg px-2.5 py-2 text-left transition-colors duration-150",
                  on ? "bg-secondary text-foreground" : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground"
                )}
              >
                <Icon className={cn("mt-0.5 size-4 shrink-0", on && "text-primary")} />
                <span className="min-w-0">
                  <span className="block text-[13px] font-medium">{label}</span>
                  <span className="block truncate text-[11px] text-muted-foreground">{hint}</span>
                </span>
              </button>
              );
            })}
          </nav>

          {/* Sherpa's status: what the guide is doing right now */}
          <div className="m-3 flex items-center gap-3 rounded-lg border border-border bg-background p-2.5">
            <Sherpa pose={busy ? "thinking" : current ? "happy" : "guide"} size={48} decorative />
            <div className="min-w-0 text-[11px] leading-snug">
              <p className="font-medium text-foreground">{busy ? "Working on it…" : current ? "Ready when you are" : "Waiting for code"}</p>
              {health && (
                <p className={cn("truncate", model ? "text-muted-foreground" : "text-warning")} title={model ? `Fallbacks: ${health.llm.fallbacks.join(", ")}` : undefined}>
                  {model ? `Model: ${model}` : "Offline mode, no model key"}
                </p>
              )}
              <button onClick={() => setPalette(true)} className="mt-0.5 hidden items-center gap-1 text-muted-foreground hover:text-foreground md:flex">
                <CommandIcon className="size-3" /> K for commands
              </button>
            </div>
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
          {/* phones: switcher + tabs instead of the sidebar */}
          <div className="border-b border-border bg-card p-2 sm:hidden">
            <RepoSwitcher repos={repos} current={current} onSelect={select} onAdd={() => setAdding(true)} className="shadow-none" />
          </div>

          <RepoBar
            current={current}
            freshness={freshness}
            adding={adding}
            onAdd={() => setAdding(true)}
            onReindex={reindex}
            onDelete={() => setConfirmDelete(true)}
            onPalette={() => setPalette(true)}
          />

          {adding && (
            // a page of its own while open: the panels underneath stay mounted but hidden
            <div className="scroll-thin min-h-0 flex-1 overflow-y-auto bg-card px-4 pb-10 sm:px-6 sm:pt-4">
              <ImportSource
                key={importUrl}
                initialUrl={importUrl}
                localAllowed={!!health?.local_ingest}
                privateTtlHours={health?.private_ttl_hours}
                onIndexed={(id) => {
                  setAdding(false);
                  setImportUrl(undefined);
                  try {
                    localStorage.setItem(LAST_REPO_KEY, id);
                  } catch {
                    /* ignore */
                  }
                  loadRepos(id);
                }}
                onCancel={current ? () => { setAdding(false); setImportUrl(undefined); } : undefined}
              />
            </div>
          )}

          <div role="tablist" aria-label="Panels" className={cn("no-scrollbar flex overflow-x-auto border-b border-border bg-card px-1 sm:hidden", adding && "hidden")}>
            {NAV.map(({ id, icon: Icon, short }) => (
              <button
                key={id}
                role="tab"
                aria-selected={tab === id}
                onClick={() => setTab(id)}
                className={cn(
                  "flex min-w-[3.75rem] flex-1 shrink-0 flex-col items-center gap-0.5 border-b-2 py-2 text-[11px] font-medium",
                  tab === id ? "border-primary text-foreground" : "border-transparent text-muted-foreground"
                )}
              >
                <Icon className="size-4" />
                {short}
              </button>
            ))}
          </div>

          {/* every panel stays mounted so results survive tab switches; keyed by repo so they reset on switch,
              and the map and tasks also reload when the index changes (the chat and tours keep their history) */}
          {(["overview", "stack", "machine", "city", "ask", "tour", "tasks", "docs", "quiz"] as TabId[]).map((id) => (
            <div key={`${id}-${repoId}${["overview", "stack", "machine", "city", "tasks", "quiz"].includes(id) ? `-${indexRev}` : ""}`} className={cn("flex min-h-0 flex-1 flex-col", (tab !== id || adding) && "hidden")}>
              {id === "ask" && <AskPanel repoId={repoId} repoName={current?.name || ""} seed={askSeed} onSeedUsed={clearAsk} />}
              {id === "stack" && (
                <StackPanel repoId={repoId} active={tab === "stack" && !adding} busy={busy} setBusy={setBusy} onAsk={askAbout} />
              )}
              {id === "city" && <CityPanel repoId={repoId} busy={busy} setBusy={setBusy} onAsk={askAbout} />}
              {id === "quiz" && <QuizPanel repoId={repoId} busy={busy} setBusy={setBusy} onAsk={askAbout} onTour={tourFlow} />}
              {id === "machine" && <MachinePanel repoId={repoId} busy={busy} setBusy={setBusy} onAsk={askAbout} />}
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

      <CommandPalette open={palette} onOpenChange={setPalette} items={paletteItems} onAsk={repoId ? askAbout : undefined} />
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={`Delete ${current?.name ?? "this repository"}?`}
        description="Its index, architecture map, tasks and docs are removed. You can import it again later."
        onConfirm={removeCurrent}
      />
    </CodeViewerProvider>
  );
}
