"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { toast } from "sonner";
import { CheckCircle2, FolderGit2, Loader2, Send } from "lucide-react";
import { api, ApiError, type Citation } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Separator, Skeleton, Tabs, Textarea } from "./ui/primitives";

type TabId = "ask" | "overview" | "tour" | "tasks";

export function Dashboard() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [repoUrl, setRepoUrl] = useState("https://github.com/gothinkster/realworld");
  const [docsUrls, setDocsUrls] = useState("");
  const [enrichWeb, setEnrichWeb] = useState(true);
  const [webNote, setWebNote] = useState("");
  const [repoId, setRepoId] = useState("");
  const [indexing, setIndexing] = useState(false);
  const [tab, setTab] = useState<TabId>("ask");
  const [question, setQuestion] = useState("How does user signup work?");
  const [answer, setAnswer] = useState("");
  const [cites, setCites] = useState<Citation[]>([]);
  const [confidence, setConfidence] = useState(0);
  const [overview, setOverview] = useState<any>(null);
  const [tour, setTour] = useState<any>(null);
  const [tasks, setTasks] = useState<any>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [keys, setKeys] = useState<{ id: string; label: string; provider: string; model: string }[]>([]);
  const [endpoints, setEndpoints] = useState<{ id: string; name: string; model: string }[]>([]);
  const [keyId, setKeyId] = useState("");
  const [endpointId, setEndpointId] = useState("");

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  useEffect(() => {
    if (user) {
      api.keys().then(setKeys).catch(() => {});
      api.endpoints().then(setEndpoints).catch(() => {});
    }
  }, [user]);

  if (loading || !user) {
    return (
      <main className="container space-y-3 py-10">
        <Skeleton className="h-10 w-64" /><Skeleton className="h-40 w-full" /><Skeleton className="h-40 w-full" />
      </main>
    );
  }

  async function run<T>(label: string, fn: () => Promise<T>, done: (v: T) => void) {
    setBusy(label);
    try {
      done(await fn());
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Request failed");
    } finally {
      setBusy(null);
    }
  }

  function doIngest() {
    setIndexing(true);
    setWebNote("");
    const urls = docsUrls.split("\n").map((s) => s.trim()).filter(Boolean);
    api.ingest(repoUrl.trim(), urls, enrichWeb)
      .then((j) => {
        setRepoId(j.repo_id);
        const web = (j.web_sources || []).filter((s) => s.status === "ok").length;
        const skipped = (j.web_sources || []).find((s) => s.status === "skipped");
        setWebNote(web ? `+ ${web} web source(s) via Firecrawl` : skipped ? "code-only (set FIRECRAWL_API_KEY for web context)" : "");
        toast.success(`Indexed ${j.files} files · ${j.chunks} chunks`);
      })
      .catch((e) => toast.error(e instanceof ApiError ? e.message : "Indexing failed"))
      .finally(() => setIndexing(false));
  }

  return (
    <main className="container space-y-6 py-8">
      {/* repo bar */}
      <Card className="animate-fade-up">
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><FolderGit2 className="size-5" /> Repository</CardTitle>
          <CardDescription>Index any public GitHub repo. Anonymous Q&A works out of the box; sign-in unlocks your keys.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 sm:flex-row">
          <Input value={repoUrl} onChange={(e) => setRepoUrl(e.target.value)} placeholder="https://github.com/org/repo" className="font-mono" />
          <Button onClick={doIngest} disabled={indexing || !repoUrl.trim()} className="shrink-0">
            {indexing && <Loader2 className="animate-spin" />} Index repo
          </Button>
        </CardContent>
        <CardContent className="space-y-3 pt-0">
          <div className="space-y-1.5">
            <p className="text-sm font-medium">Docs URLs <span className="font-normal text-muted-foreground">(optional, one per line — scraped via Firecrawl)</span></p>
            <Textarea value={docsUrls} onChange={(e) => setDocsUrls(e.target.value)} rows={2}
              placeholder="https://docs.example.com/getting-started" className="font-mono text-xs" />
          </div>
          <label className="flex cursor-pointer items-center gap-2 text-sm text-muted-foreground">
            <input type="checkbox" checked={enrichWeb} onChange={(e) => setEnrichWeb(e.target.checked)} className="size-4 accent-black" />
            Enrich with web context (repo page + docs via Firecrawl)
          </label>
        </CardContent>
        {repoId && (
          <CardContent className="pt-0">
            <Badge variant="success"><CheckCircle2 /> indexed · <span className="font-mono">{repoId}</span></Badge>
            {webNote && <p className="mt-1.5 text-xs text-muted-foreground">{webNote}</p>}
          </CardContent>
        )}
      </Card>

      {/* model selector */}
      <Card className="animate-fade-up">
        <CardContent className="flex flex-col gap-3 pt-6 sm:flex-row sm:items-end">
          <div className="flex-1 space-y-1.5">
            <p className="text-sm font-medium">Model for answers</p>
            <select value={keyId} onChange={(e) => { setKeyId(e.target.value); setEndpointId(""); }}
              className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring">
              <option value="">Offline extractive (no key needed)</option>
              {keys.map((k) => <option key={k.id} value={k.id}>{k.label} · {k.provider}/{k.model}</option>)}
            </select>
          </div>
          <div className="flex-1 space-y-1.5">
            <p className="text-sm font-medium">…or custom endpoint</p>
            <select value={endpointId} onChange={(e) => { setEndpointId(e.target.value); setKeyId(""); }}
              className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring">
              <option value="">None</option>
              {endpoints.map((e) => <option key={e.id} value={e.id}>{e.name} · {e.model}</option>)}
            </select>
          </div>
        </CardContent>
      </Card>

      {/* workspace */}
      <div className="flex flex-wrap items-center gap-3">
        <Tabs value={tab} onValueChange={(v) => setTab(v as TabId)} tabs={[
          { value: "ask", label: "Ask" }, { value: "overview", label: "Overview" },
          { value: "tour", label: "Tour" }, { value: "tasks", label: "Starter tasks" },
        ]} />
      </div>

      <AnimatePresence mode="wait">
        <motion.div key={tab} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}>
          {tab === "ask" && (
            <Card>
              <CardContent className="space-y-4 pt-6">
                <div className="flex gap-2">
                  <Textarea value={question} onChange={(e) => setQuestion(e.target.value)} rows={2}
                    placeholder="How does authentication work?" />
                  <Button disabled={!repoId || !!busy} className="shrink-0 self-end"
                    onClick={() => run("Asking Sherpa…", () => api.ask(repoId, question, keyId || undefined, endpointId || undefined),
                      (j) => { setAnswer(j.answer_markdown); setCites(j.citations); setConfidence(j.confidence); })}>
                    {busy ? <Loader2 className="animate-spin" /> : <Send />} Ask
                  </Button>
                </div>
                {!repoId && <p className="text-sm text-muted-foreground">Index a repo above first.</p>}
                {answer && (
                  <div className="animate-fade-in space-y-3">
                    <Separator />
                    <div className="flex items-center gap-2">
                      <Badge variant="secondary">confidence {(confidence * 100).toFixed(0)}%</Badge>
                      <Badge variant="success"><CheckCircle2 /> {cites.length} grounded citations</Badge>
                    </div>
                    <pre className="whitespace-pre-wrap text-sm leading-relaxed">{answer}</pre>
                    {cites.map((c, i) => (
                      <div key={i} className="rounded-lg border bg-secondary/50 p-3">
                        <code className="font-mono text-xs font-medium">{c.file}:{c.start_line}-{c.end_line}</code>
                        <pre className="code-scroll mt-1.5 overflow-x-auto whitespace-pre-wrap font-mono text-xs text-muted-foreground">{c.snippet}</pre>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {tab === "overview" && (
            <Card>
              <CardContent className="space-y-3 pt-6">
                <Button disabled={!repoId || !!busy} onClick={() => run("Mapping…", () => api.overview(repoId), setOverview)}>
                  {busy ? <Loader2 className="animate-spin" /> : null} Generate overview</Button>
                {overview && (
                  <div className="animate-fade-in space-y-3">
                    <p className="text-sm leading-relaxed">{overview.summary}</p>
                    <pre className="code-scroll overflow-x-auto rounded-lg bg-zinc-950 p-4 font-mono text-xs text-zinc-100">{overview.mermaid}</pre>
                    <ul className="space-y-1.5">
                      {overview.components.map((c: any, i: number) => (
                        <li key={i} className="rounded-md border px-3 py-2 text-sm">
                          <b>{c.name}</b> <span className="font-mono text-xs text-muted-foreground">{c.path}</span>
                          <Badge variant="outline" className="ml-2">{c.role}</Badge>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {tab === "tour" && (
            <Card>
              <CardContent className="space-y-3 pt-6">
                <div className="flex gap-2">
                  <Input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="user signup" />
                  <Button disabled={!repoId || !!busy} onClick={() => run("Building tour…", () => api.tour(repoId, question), setTour)}>
                    {busy ? <Loader2 className="animate-spin" /> : null} Build tour</Button>
                </div>
                {tour && (
                  <div className="animate-fade-in space-y-3">
                    <p className="text-sm font-medium">{tour.title} <span className="text-muted-foreground">· ~{tour.estimated_minutes} min</span></p>
                    {tour.steps.map((s: any, i: number) => (
                      <div key={i} className="rounded-lg border p-3">
                        <p className="text-sm"><b>Step {i + 1}.</b> {s.caption}</p>
                        <pre className="code-scroll mt-2 overflow-x-auto rounded-md bg-zinc-950 p-3 font-mono text-xs text-zinc-100">{s.code}</pre>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {tab === "tasks" && (
            <Card>
              <CardContent className="space-y-3 pt-6">
                <Button disabled={!repoId || !!busy} onClick={() => run("Scouting…", () => api.tasks(repoId), setTasks)}>
                  {busy ? <Loader2 className="animate-spin" /> : null} Suggest starter tasks</Button>
                {tasks && (
                  <div className="stagger space-y-3">
                    {tasks.tasks.map((t: any, i: number) => (
                      <div key={i} className="rounded-lg border p-4">
                        <div className="flex items-center gap-2">
                          <p className="font-medium">{t.title}</p>
                          <Badge variant={t.difficulty === "easy" ? "success" : "secondary"}>{t.difficulty}</Badge>
                        </div>
                        <p className="mt-1 text-sm text-muted-foreground">{t.why}</p>
                        <p className="mt-2 font-mono text-xs">{t.files.join(", ")}</p>
                        <ol className="mt-2 list-decimal space-y-0.5 pl-5 text-sm">{t.steps.map((s: string, j: number) => <li key={j}>{s}</li>)}</ol>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </motion.div>
      </AnimatePresence>
    </main>
  );
}
