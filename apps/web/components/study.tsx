"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Download, FlaskConical, Pause, Play, RotateCcw, Save, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError, type StudyResult, type StudySummary, type StudyTaskId } from "../lib/api";
import { useAuth } from "../lib/auth";
import { cn } from "../lib/utils";
import { Badge, Button, Input, Label, Textarea } from "./ui/primitives";
import { SectionLabel } from "./workspace/shared";

type Protocol = Awaited<ReturnType<typeof api.studyProtocol>>;

function fmt(sec: number) {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function Rating({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return (
    <div>
      <Label className="text-xs">{label}</Label>
      <div className="mt-1.5 flex gap-1">
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            onClick={() => onChange(n)}
            className={cn(
              "h-8 w-8 rounded-md border text-xs",
              value === n ? "border-foreground bg-foreground text-background" : "border-border text-muted-foreground hover:text-foreground"
            )}
          >
            {n}
          </button>
        ))}
      </div>
    </div>
  );
}

function Bars({ summary }: { summary: StudySummary }) {
  const max = Math.max(1, ...summary.tasks.flatMap((t) => [t.control.mean_minutes || 0, t.sherpa.mean_minutes || 0]));
  return (
    <div className="space-y-5">
      {summary.tasks.map((t) => (
        <div key={t.task}>
          <div className="mb-1.5 flex items-baseline gap-2 text-sm">
            <span className="font-medium">{t.title}</span>
            {t.time_saved_pct !== null && (
              <Badge variant={t.time_saved_pct > 0 ? "success" : "warning"} >
                {t.time_saved_pct > 0 ? `${t.time_saved_pct}% faster with Sherpa` : `${-t.time_saved_pct}% slower with Sherpa`}
              </Badge>
            )}
          </div>
          {(["control", "sherpa"] as const).map((g) => {
            const v = t[g].mean_minutes;
            return (
              <div key={g} className="flex items-center gap-2 py-0.5 text-[12px]">
                <span className="w-16 shrink-0 text-muted-foreground">{g === "control" ? "Repo only" : "Sherpa"}</span>
                <div className="h-5 flex-1 rounded bg-secondary/50">
                  {v !== null && (
                    <div
                      className={cn("flex h-5 items-center justify-end rounded pr-1.5 text-[11px] font-medium tabular-nums",
                        g === "control" ? "bg-muted-foreground/50 text-white" : "bg-primary text-primary-foreground")}
                      style={{ width: `${Math.max(8, (100 * v) / max)}%` }}
                    >
                      {v} min
                    </div>
                  )}
                </div>
                <span className="w-28 shrink-0 text-right text-muted-foreground">
                  {t[g].n ? `n=${t[g].n} · score ${t[g].mean_score}/${t.max_score}` : "no data"}
                </span>
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}

export function Study() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [protocol, setProtocol] = useState<Protocol | null>(null);
  const [rows, setRows] = useState<StudyResult[]>([]);
  const [summary, setSummary] = useState<StudySummary | null>(null);
  const [repos, setRepos] = useState<string[]>([]);

  const [participant, setParticipant] = useState("P1");
  const [group, setGroup] = useState<"control" | "sherpa">("sherpa");
  const [task, setTask] = useState<StudyTaskId>("architecture");
  const [repo, setRepo] = useState("");
  const [score, setScore] = useState(0);
  const [ratings, setRatings] = useState({ useful: 0, trustworthy: 0, reuse: 0 });
  const [notes, setNotes] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const [running, setRunning] = useState(false);
  const startRef = useRef<number>(0);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  const refresh = useCallback(async () => {
    try {
      const [r, s] = await Promise.all([api.studyResults(), api.studySummary()]);
      setRows(r);
      setSummary(s);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Couldn't load study results");
    }
  }, []);

  useEffect(() => {
    if (!user) return;
    api.studyProtocol().then(setProtocol).catch(() => toast.error("Couldn't load the study protocol"));
    api.repos().then(({ repos }) => {
      setRepos(repos.map((r) => r.name));
      setRepo((cur) => cur || repos[0]?.name || "");
    }).catch(() => {});
    refresh();
  }, [user, refresh]);

  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setElapsed((Date.now() - startRef.current) / 1000), 250);
    return () => clearInterval(t);
  }, [running]);

  function toggle() {
    if (running) {
      setRunning(false);
    } else {
      startRef.current = Date.now() - elapsed * 1000;
      setRunning(true);
    }
  }

  async function save() {
    if (elapsed < 1) return toast.error("Time the task first");
    try {
      await api.addStudyResult({
        participant, group, task, repo, seconds: Math.round(elapsed), score, notes,
        ...(group === "sherpa" ? ratings : { useful: 0, trustworthy: 0, reuse: 0 }),
      });
      toast.success(`Saved ${participant} · ${task} · ${fmt(elapsed)}`);
      setElapsed(0);
      setRunning(false);
      setScore(0);
      setNotes("");
      refresh();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Save failed");
    }
  }

  async function exportCsv() {
    const csv = await api.studyCsv();
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    Object.assign(document.createElement("a"), { href: url, download: "sherpa-user-study.csv" }).click();
    URL.revokeObjectURL(url);
  }

  if (loading || !user || !protocol) {
    return <main className="flex h-[60vh] items-center justify-center text-sm text-muted-foreground">Loading…</main>;
  }
  const maxScore = protocol.tasks[task].max_score;
  const hasData = rows.length > 0;

  return (
    <main className="container max-w-6xl space-y-8 py-8">
      <div>
        <p className="eyebrow flex items-center gap-1.5">
          <FlaskConical className="size-3.5" /> Research
        </p>
        <h1 className="mt-1 text-3xl font-semibold">Newcomer user study</h1>
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
          Does Sherpa help newcomers understand a codebase faster? Give the same tasks to two groups — one with the
          repository only, one with the repository plus Sherpa — time each task, and score it against a reference
          answer. Use pseudonyms (P1, P2…), never real names.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1.1fr_1fr]">
        <section className="space-y-4 rounded-xl border border-border bg-card p-5">
          <SectionLabel>Record a task</SectionLabel>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div>
              <Label className="text-xs">Participant</Label>
              <Input className="mt-1.5" value={participant} onChange={(e) => setParticipant(e.target.value)} />
            </div>
            <div>
              <Label className="text-xs">Group</Label>
              <div className="mt-1.5 flex rounded-lg border border-border p-0.5">
                {(["control", "sherpa"] as const).map((g) => (
                  <button
                    key={g}
                    onClick={() => setGroup(g)}
                    className={cn("flex-1 rounded-md py-1.5 text-xs", group === g ? "bg-secondary font-medium" : "text-muted-foreground")}
                  >
                    {g === "control" ? "Repo only" : "Sherpa"}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <Label className="text-xs">Repository</Label>
              <select
                value={repo}
                onChange={(e) => setRepo(e.target.value)}
                className="mt-1.5 h-9 w-full rounded-lg border border-input bg-transparent px-2 text-sm"
              >
                {repos.map((r) => (
                  <option key={r} value={r} className="bg-background">{r}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="space-y-2">
            {(Object.keys(protocol.tasks) as StudyTaskId[]).map((id) => (
              <button
                key={id}
                onClick={() => {
                  setTask(id);
                  setScore(0);
                }}
                className={cn(
                  "w-full rounded-lg border px-4 py-3 text-left",
                  task === id ? "border-foreground/40 bg-secondary/60" : "border-border hover:bg-secondary/30"
                )}
              >
                <p className="text-sm font-medium">{protocol.tasks[id].title}</p>
                <p className="text-xs text-muted-foreground">{protocol.tasks[id].prompt}</p>
              </button>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-3 rounded-lg border border-border px-4 py-3">
            <span className="font-mono text-2xl tabular-nums">{fmt(elapsed)}</span>
            <Button size="sm" onClick={toggle} variant={running ? "secondary" : "default"}>
              {running ? <Pause className="size-3.5" /> : <Play className="size-3.5" />}
              {running ? "Pause" : elapsed ? "Resume" : "Start"}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => { setRunning(false); setElapsed(0); }}>
              <RotateCcw className="size-3.5" />
            </Button>
            <div className="ml-auto flex items-center gap-2">
              <Label className="text-xs">Score</Label>
              <div className="flex gap-1">
                {Array.from({ length: maxScore + 1 }, (_, n) => (
                  <button
                    key={n}
                    onClick={() => setScore(n)}
                    className={cn("h-8 w-8 rounded-md border text-xs",
                      score === n ? "border-foreground bg-foreground text-background" : "border-border text-muted-foreground")}
                  >
                    {n}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {group === "sherpa" && (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <Rating label="Sherpa was useful" value={ratings.useful} onChange={(v) => setRatings((r) => ({ ...r, useful: v }))} />
              <Rating label="I trusted its answers" value={ratings.trustworthy} onChange={(v) => setRatings((r) => ({ ...r, trustworthy: v }))} />
              <Rating label="I'd use it again" value={ratings.reuse} onChange={(v) => setRatings((r) => ({ ...r, reuse: v }))} />
            </div>
          )}
          <Textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Observations, quotes, where they got stuck…"
            className="min-h-[64px]"
          />
          <Button onClick={save} className="w-full">
            <Save className="size-4" /> Save result
          </Button>
          <p className="text-[11px] text-muted-foreground">{protocol.rubric}</p>
        </section>

        <section className="space-y-4 rounded-xl border border-border bg-card p-5">
          <div className="flex items-center gap-2">
            <SectionLabel className="mb-0 mr-auto">Results</SectionLabel>
            {summary && (
              <span className="text-[11px] text-muted-foreground">
                {summary.participants.control} control · {summary.participants.sherpa} Sherpa participants
              </span>
            )}
          </div>
          {!hasData || !summary ? (
            <p className="py-10 text-center text-sm text-muted-foreground">
              No sessions recorded yet. Results appear here once you run the study with real participants.
            </p>
          ) : (
            <>
              <Bars summary={summary} />
              {summary.satisfaction.useful !== null && (
                <div className="flex flex-wrap gap-2 border-t border-border pt-3 text-[12px]">
                  <Badge variant="outline" className="font-normal">useful {summary.satisfaction.useful}/5</Badge>
                  <Badge variant="outline" className="font-normal">trustworthy {summary.satisfaction.trustworthy}/5</Badge>
                  <Badge variant="outline" className="font-normal">would reuse {summary.satisfaction.reuse}/5</Badge>
                </div>
              )}
              {(summary.participants.control < 3 || summary.participants.sherpa < 3) && (
                <p className="text-[11px] text-warning">
                  Small sample — report these as indicative, not statistically significant.
                </p>
              )}
            </>
          )}
        </section>
      </div>

      {hasData && (
        <section>
          <div className="mb-2 flex items-center">
            <SectionLabel className="mb-0 mr-auto">Raw data</SectionLabel>
            <Button size="sm" variant="outline" onClick={exportCsv}>
              <Download className="size-3.5" /> Export CSV
            </Button>
          </div>
          <div className="overflow-x-auto rounded-xl border border-border">
            <table className="w-full text-left text-xs">
              <thead className="bg-secondary/60 text-muted-foreground">
                <tr>
                  {["Participant", "Group", "Task", "Repo", "Time", "Score", "Ratings", "Notes", ""].map((h) => (
                    <th key={h} className="px-3 py-2 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-t border-border/60 align-top">
                    <td className="px-3 py-2 font-medium">{r.participant}</td>
                    <td className="px-3 py-2">{r.group === "control" ? "Repo only" : "Sherpa"}</td>
                    <td className="px-3 py-2">{r.task}</td>
                    <td className="px-3 py-2 text-muted-foreground">{r.repo}</td>
                    <td className="px-3 py-2 font-mono">{fmt(r.seconds)}</td>
                    <td className="px-3 py-2">{r.score}/{r.max_score}</td>
                    <td className="px-3 py-2 text-muted-foreground">
                      {r.group === "sherpa" && r.useful ? `${r.useful}/${r.trustworthy}/${r.reuse}` : "—"}
                    </td>
                    <td className="max-w-xs px-3 py-2 text-muted-foreground">{r.notes}</td>
                    <td className="px-3 py-2">
                      <button
                        onClick={async () => {
                          await api.deleteStudyResult(r.id);
                          refresh();
                        }}
                        className="text-muted-foreground hover:text-destructive"
                        title="Delete"
                      >
                        <Trash2 className="size-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </main>
  );
}
