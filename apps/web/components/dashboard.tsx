"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { toast } from "sonner";
import {
  ArrowUp,
  CheckCircle2,
  ChevronRight,
  Code2,
  FileCode2,
  FolderGit2,
  ListTodo,
  Map,
  MessageSquare,
  Route,
  Settings2,
  Sparkles,
} from "lucide-react";
import { api, ApiError, type Citation } from "../lib/api";
import { useAuth } from "../lib/auth";
import { SherpaAvatar, SherpaOrb, TypingIndicator } from "./sherpa-orb";
import {
  Badge,
  Button,
  Input,
  Textarea,
} from "./ui/primitives";
import { cn } from "../lib/utils";

/* ── types ── */
type TabId = "ask" | "overview" | "tour" | "tasks";

interface ChatMessage {
  id: string;
  role: "user" | "sherpa";
  text: string;
  citations?: Citation[];
  confidence?: number;
}

/* ── sidebar nav items ── */
const NAV = [
  { id: "ask" as TabId, icon: MessageSquare, label: "Ask Sherpa" },
  { id: "overview" as TabId, icon: Map, label: "Architecture" },
  { id: "tour" as TabId, icon: Route, label: "Code Tour" },
  { id: "tasks" as TabId, icon: ListTodo, label: "Starter Tasks" },
];

/* ── animation easing ── */
const ease = [0.22, 1, 0.36, 1] as const;

/* ── helpers ── */
function uid() {
  return Math.random().toString(36).slice(2);
}

/* ── Citation chip ── */
function CitationChip({ c }: { c: Citation }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="w-full">
      <button
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-lg border border-border/60 bg-secondary/60 px-2.5 py-1.5",
          "text-left font-mono text-[10px] text-muted-foreground",
          "transition-colors hover:border-border hover:text-foreground"
        )}
      >
        <FileCode2 className="size-3 shrink-0" />
        {c.file}:{c.start_line}-{c.end_line}
        <ChevronRight
          className={cn("size-3 shrink-0 transition-transform duration-200", open && "rotate-90")}
        />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease }}
            className="overflow-hidden"
          >
            <pre className="code-scroll mt-1 overflow-x-auto rounded-lg bg-black/40 px-4 py-3 font-mono text-[11px] leading-relaxed text-zinc-300">
              {c.snippet}
            </pre>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ── Message bubble ── */
function MessageBubble({ msg, isLast }: { msg: ChatMessage; isLast: boolean }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.3, ease }}
      className={cn("flex gap-3", msg.role === "user" ? "justify-end" : "justify-start")}
    >
      {msg.role === "sherpa" && (
        <SherpaAvatar state={isLast ? "responding" : "idle"} className="mt-1 shrink-0" />
      )}
      <div className={cn("max-w-[80%] space-y-2", msg.role === "user" ? "items-end" : "items-start")}>
        <div
          className={cn(
            "rounded-2xl px-4 py-3 text-sm leading-relaxed",
            msg.role === "user"
              ? "rounded-tr-sm bg-primary text-primary-foreground"
              : "rounded-tl-sm border border-border bg-card text-card-foreground"
          )}
        >
          <p style={{ whiteSpace: "pre-wrap" }}>{msg.text}</p>
        </div>

        {/* citations */}
        {msg.citations && msg.citations.length > 0 && (
          <div className="space-y-1.5 w-full">
            {msg.confidence !== undefined && (
              <div className="flex items-center gap-2">
                <Badge variant="success" className="text-[10px]">
                  <CheckCircle2 className="size-2.5" />
                  {(msg.confidence * 100).toFixed(0)}% confidence
                </Badge>
                <Badge variant="secondary" className="text-[10px]">
                  {msg.citations.length} source{msg.citations.length > 1 ? "s" : ""}
                </Badge>
              </div>
            )}
            {msg.citations.map((c, i) => (
              <CitationChip key={i} c={c} />
            ))}
          </div>
        )}
      </div>
    </motion.div>
  );
}

/* ── Repo bar ── */
function RepoBar({
  repoUrl, setRepoUrl, onIndex, indexing, repoId, webNote,
}: {
  repoUrl: string;
  setRepoUrl: (v: string) => void;
  onIndex: () => void;
  indexing: boolean;
  repoId: string;
  webNote: string;
}) {
  const [expanded, setExpanded] = useState(!repoId);

  return (
    <div className="border-b border-border bg-card/60 px-4 py-3">
      <div className="flex items-center gap-3">
        <FolderGit2 className="size-4 shrink-0 text-muted-foreground" />
        {repoId ? (
          <div className="flex min-w-0 flex-1 items-center gap-2">
            <span className="min-w-0 truncate font-mono text-xs text-muted-foreground">
              {repoUrl}
            </span>
            <Badge variant="success" className="shrink-0 text-[10px]">
              <CheckCircle2 className="size-2.5" /> indexed
            </Badge>
            {webNote && (
              <span className="hidden shrink-0 text-[10px] text-muted-foreground sm:block">
                {webNote}
              </span>
            )}
          </div>
        ) : (
          <span className="text-sm text-muted-foreground">No repo indexed</span>
        )}
        <button
          onClick={() => setExpanded((v) => !v)}
          className="ml-auto rounded-md p-1 text-muted-foreground transition-colors hover:text-foreground"
        >
          <Settings2 className="size-4" />
        </button>
      </div>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease }}
            className="overflow-hidden"
          >
            <div className="mt-3 flex gap-2">
              <Input
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
                placeholder="https://github.com/org/repo"
                className="flex-1 font-mono text-xs"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && repoUrl.trim() && !indexing) onIndex();
                }}
              />
              <Button
                onClick={onIndex}
                disabled={indexing || !repoUrl.trim()}
                size="sm"
                className="shrink-0"
              >
                {indexing ? (
                  <span className="flex items-center gap-1.5">
                    <span className="inline-flex gap-1">
                      {[0, 1, 2].map((i) => (
                        <motion.span
                          key={i}
                          className="block h-1 w-1 rounded-full bg-primary-foreground"
                          animate={{ y: [0, -3, 0] }}
                          transition={{ duration: 0.8, delay: i * 0.15, repeat: Infinity }}
                        />
                      ))}
                    </span>
                    Indexing
                  </span>
                ) : (
                  "Index repo"
                )}
              </Button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ── Overview panel ── */
function OverviewPanel({ repoId, busy, setBusy }: { repoId: string; busy: string | null; setBusy: (v: string | null) => void }) {
  const [data, setData] = useState<any>(null);

  async function generate() {
    setBusy("overview");
    try {
      setData(await api.overview(repoId));
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="flex-1 overflow-y-auto custom-scroll p-6">
        {!data ? (
          <div className="flex flex-col items-center justify-center gap-6 py-16 text-center">
            <SherpaOrb size="lg" state={busy === "overview" ? "thinking" : "idle"} />
            <div>
              <h3 className="font-semibold">Architecture map</h3>
              <p className="mt-1 text-sm text-muted-foreground max-w-sm">
                Sherpa will analyze the repo structure and generate a Mermaid component diagram.
              </p>
            </div>
            <Button onClick={generate} disabled={!repoId || !!busy}>
              <Map className="size-4" />
              {busy === "overview" ? "Mapping…" : "Generate overview"}
            </Button>
            {!repoId && (
              <p className="text-xs text-muted-foreground">Index a repo first.</p>
            )}
          </div>
        ) : (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, ease }}
            className="space-y-6"
          >
            <p className="text-sm leading-relaxed text-muted-foreground">{data.summary}</p>

            <div>
              <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Diagram
              </h3>
              <pre className="code-scroll overflow-x-auto rounded-xl bg-black/60 p-4 font-mono text-xs text-zinc-300 leading-relaxed">
                {data.mermaid}
              </pre>
            </div>

            <div>
              <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Components
              </h3>
              <div className="space-y-2">
                {data.components.map((c: any, i: number) => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.04, duration: 0.3, ease }}
                    className="flex items-center gap-3 rounded-xl border border-border bg-card px-4 py-3"
                  >
                    <Code2 className="size-4 shrink-0 text-muted-foreground" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium text-sm">{c.name}</p>
                      <p className="truncate font-mono text-xs text-muted-foreground">{c.path}</p>
                    </div>
                    <Badge variant="outline" className="shrink-0 text-[10px]">{c.role}</Badge>
                  </motion.div>
                ))}
              </div>
            </div>
          </motion.div>
        )}
      </div>
    </div>
  );
}

/* ── Tour panel ── */
function TourPanel({ repoId, busy, setBusy }: { repoId: string; busy: string | null; setBusy: (v: string | null) => void }) {
  const [flow, setFlow] = useState("user signup");
  const [tour, setTour] = useState<any>(null);

  async function build() {
    setBusy("tour");
    try {
      setTour(await api.tour(repoId, flow));
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="border-b border-border px-4 py-3">
        <div className="flex gap-2">
          <Input
            value={flow}
            onChange={(e) => setFlow(e.target.value)}
            placeholder="e.g. user signup, payment flow, auth"
            className="text-sm"
            onKeyDown={(e) => {
              if (e.key === "Enter" && flow.trim() && repoId && !busy) build();
            }}
          />
          <Button onClick={build} disabled={!repoId || !!busy || !flow.trim()} size="sm">
            <Route className="size-4" />
            {busy === "tour" ? "Building…" : "Build tour"}
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto custom-scroll p-6">
        {!tour ? (
          <div className="flex flex-col items-center justify-center gap-4 py-16 text-center">
            <SherpaOrb size="lg" state={busy === "tour" ? "thinking" : "idle"} />
            <p className="text-sm text-muted-foreground max-w-sm">
              Enter a feature or flow above. Sherpa will trace it through the codebase step by step.
            </p>
          </div>
        ) : (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="space-y-4"
          >
            <div className="flex items-center gap-3">
              <h3 className="font-semibold">{tour.title}</h3>
              <Badge variant="secondary" className="text-[10px]">
                ~{tour.estimated_minutes} min
              </Badge>
            </div>

            {tour.steps.map((s: any, i: number) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.06, duration: 0.35, ease }}
                className="rounded-xl border border-border bg-card overflow-hidden"
              >
                <div className="flex items-center gap-3 border-b border-border px-4 py-3">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-secondary text-xs font-medium">
                    {i + 1}
                  </span>
                  <p className="text-sm font-medium">{s.caption}</p>
                  <span className="ml-auto font-mono text-[10px] text-muted-foreground">
                    {s.file}:{s.start_line}-{s.end_line}
                  </span>
                </div>
                <pre className="code-scroll overflow-x-auto bg-black/50 px-4 py-3 font-mono text-[11px] leading-relaxed text-zinc-300">
                  {s.code}
                </pre>
              </motion.div>
            ))}
          </motion.div>
        )}
      </div>
    </div>
  );
}

/* ── Tasks panel ── */
function TasksPanel({ repoId, busy, setBusy }: { repoId: string; busy: string | null; setBusy: (v: string | null) => void }) {
  const [tasks, setTasks] = useState<any>(null);

  async function suggest() {
    setBusy("tasks");
    try {
      setTasks(await api.tasks(repoId));
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="flex-1 overflow-y-auto custom-scroll p-6">
        {!tasks ? (
          <div className="flex flex-col items-center justify-center gap-6 py-16 text-center">
            <SherpaOrb size="lg" state={busy === "tasks" ? "thinking" : "idle"} />
            <div>
              <h3 className="font-semibold">Starter tasks</h3>
              <p className="mt-1 text-sm text-muted-foreground max-w-sm">
                Sherpa will find beginner-friendly tasks from the actual codebase with clear steps to complete them.
              </p>
            </div>
            <Button onClick={suggest} disabled={!repoId || !!busy}>
              <ListTodo className="size-4" />
              {busy === "tasks" ? "Scouting…" : "Suggest tasks"}
            </Button>
          </div>
        ) : (
          <div className="space-y-4">
            {tasks.tasks.map((t: any, i: number) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.07, duration: 0.35, ease }}
                className="rounded-xl border border-border bg-card p-5"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1">
                    <p className="font-medium">{t.title}</p>
                    <p className="mt-1 text-sm text-muted-foreground">{t.why}</p>
                  </div>
                  <Badge
                    variant={t.difficulty === "easy" ? "success" : "secondary"}
                    className="shrink-0 text-[10px]"
                  >
                    {t.difficulty}
                  </Badge>
                </div>

                <div className="mt-3 flex flex-wrap gap-1.5">
                  {t.files.map((f: string, j: number) => (
                    <span
                      key={j}
                      className="inline-flex items-center gap-1 rounded-md border border-border/60 bg-secondary/60 px-2 py-0.5 font-mono text-[10px] text-muted-foreground"
                    >
                      <FileCode2 className="size-2.5" />
                      {f}
                    </span>
                  ))}
                </div>

                <ol className="mt-3 space-y-1 text-sm text-muted-foreground">
                  {t.steps.map((s: string, j: number) => (
                    <li key={j} className="flex items-start gap-2">
                      <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-secondary text-[9px] font-medium text-foreground">
                        {j + 1}
                      </span>
                      {s}
                    </li>
                  ))}
                </ol>
              </motion.div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Ask / Chat panel ── */
function AskPanel({ repoId }: { repoId: string }) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: uid(),
      role: "sherpa",
      text: "Hi! I'm Sherpa — your AI guide through this codebase. Index a repository above and ask me anything about how it works.",
    },
  ]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, thinking]);

  async function send() {
    const q = input.trim();
    if (!q || thinking) return;
    if (!repoId) {
      toast.error("Index a repo first");
      return;
    }

    setInput("");
    const userMsg: ChatMessage = { id: uid(), role: "user", text: q };
    setMessages((prev) => [...prev, userMsg]);
    setThinking(true);

    try {
      const resp = await api.ask(repoId, q);
      const sherpaMsg: ChatMessage = {
        id: uid(),
        role: "sherpa",
        text: resp.answer_markdown,
        citations: resp.citations,
        confidence: resp.confidence,
      };
      setMessages((prev) => [...prev, sherpaMsg]);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Request failed");
      setMessages((prev) => [
        ...prev,
        {
          id: uid(),
          role: "sherpa",
          text: "Sorry, I ran into an error. Please try again.",
        },
      ]);
    } finally {
      setThinking(false);
    }
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {/* messages */}
      <div className="flex-1 overflow-y-auto custom-scroll p-4 space-y-4">
        {messages.map((msg, i) => (
          <MessageBubble
            key={msg.id}
            msg={msg}
            isLast={i === messages.length - 1 && !thinking}
          />
        ))}
        {thinking && (
          <div className="flex items-start gap-3">
            <SherpaAvatar state="thinking" className="mt-1 shrink-0" />
            <TypingIndicator />
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* input area */}
      <div className="border-t border-border bg-card/60 p-4">
        <div className="flex items-end gap-2 rounded-xl border border-border bg-background px-3 py-2 focus-within:ring-2 focus-within:ring-ring transition-shadow">
          <Textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={repoId ? "Ask Sherpa anything about this codebase…" : "Index a repo to start asking questions"}
            rows={1}
            className="flex-1 resize-none border-0 bg-transparent p-0 text-sm shadow-none focus-visible:ring-0 min-h-[20px] max-h-[120px]"
            disabled={!repoId || thinking}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
          />
          <Button
            size="icon-sm"
            onClick={send}
            disabled={!repoId || !input.trim() || thinking}
            className="shrink-0 rounded-lg"
          >
            <ArrowUp className="size-4" />
          </Button>
        </div>
        <p className="mt-1.5 text-center text-[10px] text-muted-foreground">
          Shift+Enter for new line · Enter to send
        </p>
      </div>
    </div>
  );
}

/* ── Main Dashboard ── */
export function Dashboard() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [repoUrl, setRepoUrl] = useState("https://github.com/gothinkster/realworld");
  const [repoId, setRepoId] = useState("");
  const [indexing, setIndexing] = useState(false);
  const [webNote, setWebNote] = useState("");
  const [tab, setTab] = useState<TabId>("ask");
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

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

  function doIngest() {
    setIndexing(true);
    setWebNote("");
    api
      .ingest(repoUrl.trim(), [], true)
      .then((j) => {
        setRepoId(j.repo_id);
        const web = (j.web_sources || []).filter((s) => s.status === "ok").length;
        const skipped = (j.web_sources || []).find((s) => s.status === "skipped");
        setWebNote(
          web
            ? `+ ${web} web source(s)`
            : skipped
            ? "code-only (no Firecrawl key)"
            : ""
        );
        toast.success(`Indexed ${j.files} files · ${j.chunks} chunks`);
      })
      .catch((e) => toast.error(e instanceof ApiError ? e.message : "Indexing failed"))
      .finally(() => setIndexing(false));
  }

  return (
    <div className="flex h-[calc(100vh-3.5rem)]">
      {/* ── Sidebar ── */}
      <aside className="hidden w-56 shrink-0 flex-col border-r border-border bg-card/40 sm:flex">
        {/* Sherpa branding */}
        <div className="flex items-center gap-3 border-b border-border px-4 py-5">
          <SherpaOrb size="sm" state={busy ? "thinking" : "idle"} />
          <div>
            <p className="text-sm font-semibold">Sherpa</p>
            <p className="text-[10px] text-muted-foreground">AI Codebase Guide</p>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 space-y-0.5 p-2 pt-3">
          {NAV.map(({ id, icon: Icon, label }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={cn(
                "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors duration-150",
                tab === id
                  ? "bg-secondary text-foreground"
                  : "text-muted-foreground hover:bg-secondary/50 hover:text-foreground"
              )}
            >
              <Icon className="size-4 shrink-0" />
              {label}
            </button>
          ))}
        </nav>

        {/* Powered by badge */}
        <div className="border-t border-border p-3">
          <div className="flex items-center gap-1.5 rounded-lg border border-border/40 bg-secondary/30 px-3 py-2">
            <Sparkles className="size-3 shrink-0 text-sherpa-glow" />
            <span className="text-[10px] text-muted-foreground">Powered by</span>
            <span className="text-[10px] font-medium text-foreground">Sherpa AI</span>
          </div>
        </div>

        {/* User */}
        <div className="border-t border-border px-3 py-3">
          <div className="flex items-center gap-2.5 rounded-lg px-1 py-1.5">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-secondary text-xs font-medium uppercase">
              {(user.name || user.email).slice(0, 1)}
            </div>
            <div className="min-w-0">
              <p className="truncate text-xs font-medium">{user.name || user.email}</p>
              {user.name && (
                <p className="truncate text-[10px] text-muted-foreground">{user.email}</p>
              )}
            </div>
          </div>
        </div>
      </aside>

      {/* ── Main content ── */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Repo bar */}
        <RepoBar
          repoUrl={repoUrl}
          setRepoUrl={setRepoUrl}
          onIndex={doIngest}
          indexing={indexing}
          repoId={repoId}
          webNote={webNote}
        />

        {/* mobile tab bar */}
        <div className="flex border-b border-border bg-card/40 px-2 sm:hidden">
          {NAV.map(({ id, icon: Icon, label }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={cn(
                "flex flex-1 flex-col items-center gap-0.5 py-2 text-[10px] font-medium transition-colors",
                tab === id ? "text-foreground" : "text-muted-foreground"
              )}
            >
              <Icon className="size-4" />
              {label.split(" ")[0]}
            </button>
          ))}
        </div>

        {/* panels */}
        <AnimatePresence mode="wait">
          <motion.div
            key={tab}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.22, ease }}
            className="flex flex-1 flex-col overflow-hidden"
          >
            {tab === "ask" && (
              <AskPanel repoId={repoId} />
            )}
            {tab === "overview" && (
              <OverviewPanel repoId={repoId} busy={busy} setBusy={setBusy} />
            )}
            {tab === "tour" && (
              <TourPanel repoId={repoId} busy={busy} setBusy={setBusy} />
            )}
            {tab === "tasks" && (
              <TasksPanel repoId={repoId} busy={busy} setBusy={setBusy} />
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
