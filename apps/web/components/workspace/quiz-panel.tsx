"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, Check, GraduationCap, MessageSquare, RefreshCw, Route, ShieldCheck, X } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError, type Quiz, type QuizAttempt, type QuizResult } from "../../lib/api";
import { CitationChip } from "../code-viewer";
import { Markdown } from "../markdown";
import { Sherpa } from "../sherpa";
import { Badge, Button } from "../ui/primitives";
import { cn } from "../../lib/utils";
import { EmptyState, FadeIn, ModeBadge, SectionLabel } from "./shared";

const LETTERS = "ABCD";
const WAIT = ["Reading the code…", "Writing questions about how it works…", "Checking every answer against the code…", "Almost ready…"];

/** `inline code` inside a question or option, without a full markdown block */
function Inline({ text }: { text: string }) {
  return (
    <>
      {text.split(/(`[^`]+`)/g).map((p, i) =>
        p.startsWith("`") && p.endsWith("`") ? <code key={i}>{p.slice(1, -1)}</code> : <span key={i}>{p}</span>,
      )}
    </>
  );
}

function Ring({ percent }: { percent: number }) {
  const r = 34, c = 2 * Math.PI * r;
  return (
    <svg viewBox="0 0 80 80" className="size-24 -rotate-90" aria-hidden>
      <circle cx="40" cy="40" r={r} fill="none" strokeWidth="7" className="stroke-secondary" />
      <circle cx="40" cy="40" r={r} fill="none" strokeWidth="7" strokeLinecap="round" className="stroke-primary transition-all duration-700"
        strokeDasharray={c} strokeDashoffset={c * (1 - percent / 100)} />
    </svg>
  );
}

export function QuizPanel({
  repoId,
  busy,
  setBusy,
  onAsk,
  onTour,
}: {
  repoId: string;
  busy: string | null;
  setBusy: (v: string | null) => void;
  onAsk: (q: string) => void;
  onTour: (flow: string) => void;
}) {
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [step, setStep] = useState<"intro" | "question" | "result">("intro");
  const [at, setAt] = useState(0);
  const [answers, setAnswers] = useState<(number | null)[]>([]);
  const [started, setStarted] = useState(0);
  const [result, setResult] = useState<QuizResult | null>(null);
  const [attempts, setAttempts] = useState<QuizAttempt[]>([]);
  const [wait, setWait] = useState(0);
  const loading = busy === "quiz";

  const loadAttempts = useCallback(() => {
    if (repoId) api.quizAttempts(repoId).then((r) => setAttempts(r.attempts)).catch(() => {});
  }, [repoId]);
  useEffect(loadAttempts, [loadAttempts]);

  useEffect(() => {
    if (!loading) return setWait(0);
    const id = window.setInterval(() => setWait((w) => Math.min(WAIT.length - 1, w + 1)), 5500);
    return () => window.clearInterval(id);
  }, [loading]);

  async function load(fresh: boolean) {
    setBusy("quiz");
    try {
      const q = await api.quiz(repoId, fresh);
      if (!q.questions.length) throw new ApiError(422, "Couldn't write questions for this code yet");
      setQuiz(q);
      setStep("intro");
      setResult(null);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed to build the skill check");
    } finally {
      setBusy(null);
    }
  }

  function begin() {
    if (!quiz) return;
    setAnswers(quiz.questions.map(() => null));
    setAt(0);
    setStarted(Date.now());
    setStep("question");
  }

  async function submit() {
    if (!quiz) return;
    const missing = answers.filter((a) => a == null).length;
    if (missing && !window.confirm(`${missing} question${missing > 1 ? "s are" : " is"} unanswered. Submit anyway?`)) return;
    setBusy("quiz-submit");
    try {
      const r = await api.submitQuiz(repoId, quiz.id, answers, (Date.now() - started) / 1000);
      setResult(r);
      setStep("result");
      loadAttempts();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Couldn't submit your answers");
      if (e instanceof ApiError && e.status === 409) setQuiz(null);
    } finally {
      setBusy(null);
    }
  }

  // keys while answering: 1-4 or A-D to choose, arrows / Enter to move
  useEffect(() => {
    if (step !== "question" || !quiz) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement || e.metaKey || e.ctrlKey) return;
      const k = e.key.toUpperCase();
      const pick = "1234".includes(k) && k ? Number(k) - 1 : LETTERS.indexOf(k);
      if (k.length === 1 && pick >= 0 && pick < 4) {
        setAnswers((a) => a.map((x, i) => (i === at ? pick : x)));
      } else if (e.key === "ArrowRight" || e.key === "Enter") {
        if (at < quiz.questions.length - 1) setAt(at + 1);
        else if (e.key === "Enter") void submit();
      } else if (e.key === "ArrowLeft") setAt(Math.max(0, at - 1));
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, quiz, at, answers]);

  if (!quiz || (loading && step !== "result")) {
    return (
      <div className="scroll-thin flex-1 overflow-y-auto p-6">
        <EmptyState
          busy={loading}
          pose="analyzing"
          title={loading ? WAIT[wait] : "Skill check"}
          body={
            loading
              ? "Each question is written from this repo's own code, then answered again from the cited code alone. Questions where the two answers disagree are thrown out."
              : "Find out how well you know this codebase: 8 questions about where things live, what parts do and how data moves. Every answer is backed by the code, and you'll see which areas to explore next."
          }
        >
          {!loading && (
            <Button onClick={() => load(false)} disabled={!repoId || !!busy}>
              <GraduationCap className="size-4" /> Start a skill check
            </Button>
          )}
          {!repoId && <p className="text-xs text-muted-foreground">Index a repo first.</p>}
          {!loading && attempts.length > 0 && <History attempts={attempts} />}
        </EmptyState>
      </div>
    );
  }

  if (step === "intro") {
    return (
      <div className="scroll-thin flex-1 overflow-y-auto">
        <FadeIn className="mx-auto max-w-2xl space-y-5 p-4 sm:p-6">
          <div className="rounded-xl border border-border bg-card p-6">
            <div className="flex items-start gap-4">
              <Sherpa pose="guide" size={72} decorative />
              <div className="min-w-0 flex-1">
                <h2 className="text-lg font-semibold">Skill check</h2>
                <p className="mt-1 text-[14px] text-muted-foreground">
                  {quiz.questions.length} questions · about {quiz.minutes} minutes · {quiz.areas.length} areas of the code
                </p>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {quiz.checked && (
                    <Badge variant="success" title="A second pass answered every question from its cited code alone and agreed">
                      <ShieldCheck /> every answer checked against the code
                    </Badge>
                  )}
                  <ModeBadge mode={quiz.mode} model={quiz.model} />
                </div>
              </div>
            </div>
            <ul className="mt-5 flex flex-wrap gap-1.5">
              {quiz.areas.map((a) => (
                <li key={a.key} className="rounded-full border border-border px-2.5 py-0.5 text-[12px] text-muted-foreground">{a.name}</li>
              ))}
            </ul>
            <p className="mt-5 text-[13px] text-muted-foreground">
              Answer with the mouse or keys <kbd>1</kbd>–<kbd>4</kbd>; <kbd>←</kbd> <kbd>→</kbd> move between questions. You see the answers,
              with the code that proves them, when you submit.
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              <Button onClick={begin}>Begin <ArrowRight className="size-4" /></Button>
              <Button variant="ghost" onClick={() => load(true)} disabled={!!busy}>
                <RefreshCw className="size-3.5" /> New questions
              </Button>
            </div>
          </div>
          {attempts.length > 0 && <History attempts={attempts} />}
        </FadeIn>
      </div>
    );
  }

  if (step === "question") {
    const q = quiz.questions[at];
    const done = answers.filter((a) => a != null).length;
    const last = at === quiz.questions.length - 1;
    return (
      <div className="scroll-thin flex-1 overflow-y-auto">
        <div className="mx-auto max-w-2xl space-y-4 p-4 sm:p-6">
          <div className="flex items-center gap-3 text-[12px] tabular-nums text-muted-foreground">
            <span>Question {at + 1} of {quiz.questions.length}</span>
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-secondary" role="progressbar" aria-valuenow={done} aria-valuemax={quiz.questions.length}>
              <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${(done / quiz.questions.length) * 100}%` }} />
            </div>
            <span>{done} answered</span>
          </div>
          <FadeIn key={q.n} className="rounded-xl border border-border bg-card p-5 sm:p-6">
            <p className="eyebrow">{q.area_name} · {q.difficulty}</p>
            <h2 className="mt-2 text-[17px] font-semibold leading-snug"><Inline text={q.question} /></h2>
            <div className="mt-5 grid gap-2" role="radiogroup" aria-label={q.question}>
              {q.options.map((o, i) => {
                const on = answers[at] === i;
                return (
                  <button
                    key={i}
                    role="radio"
                    aria-checked={on}
                    onClick={() => setAnswers((a) => a.map((x, j) => (j === at ? i : x)))}
                    className={cn(
                      "flex items-start gap-3 rounded-lg border px-3.5 py-3 text-left text-[14px] transition-colors",
                      on ? "border-primary bg-primary/5" : "border-border hover:border-primary/40 hover:bg-secondary/50",
                    )}
                  >
                    <span className={cn("grid size-6 shrink-0 place-items-center rounded-md border font-mono text-[12px]",
                      on ? "border-primary bg-primary text-primary-foreground" : "border-border text-muted-foreground")}>
                      {LETTERS[i]}
                    </span>
                    <span className="min-w-0 break-words pt-0.5"><Inline text={o} /></span>
                  </button>
                );
              })}
            </div>
          </FadeIn>
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={() => setAt(Math.max(0, at - 1))} disabled={at === 0}>
              <ArrowLeft className="size-4" /> Back
            </Button>
            <div className="flex flex-1 justify-center gap-1">
              {quiz.questions.map((_, i) => (
                <button key={i} aria-label={`Question ${i + 1}`} onClick={() => setAt(i)}
                  className={cn("size-2.5 rounded-full transition-colors", i === at ? "bg-primary" : answers[i] != null ? "bg-primary/40" : "bg-secondary")} />
              ))}
            </div>
            {last ? (
              <Button onClick={submit} disabled={busy === "quiz-submit"}>
                {busy === "quiz-submit" ? "Scoring…" : "Submit"} <Check className="size-4" />
              </Button>
            ) : (
              <Button onClick={() => setAt(at + 1)}>Next <ArrowRight className="size-4" /></Button>
            )}
          </div>
        </div>
      </div>
    );
  }

  const r = result!;
  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-3xl space-y-6 p-4 sm:p-6">
        <FadeIn className="rounded-xl border border-border bg-card p-6">
          <div className="flex flex-wrap items-center gap-6">
            <div className="relative grid place-items-center">
              <Ring percent={r.percent} />
              <span className="absolute text-xl font-semibold tabular-nums">{r.percent}%</span>
            </div>
            <div className="min-w-0 flex-1">
              <p className="eyebrow">Your result</p>
              <h2 className="text-xl font-semibold">{r.level}</h2>
              <p className="mt-1 text-[14px] text-muted-foreground">
                {r.correct} of {r.total} right
                {r.weak.length > 0 ? ` · explore ${r.weak.map((w) => w.name).join(", ")} next` : " · every area covered"}
              </p>
            </div>
            <Button variant="outline" onClick={() => load(true)} disabled={!!busy}>
              <RefreshCw className="size-3.5" /> Retake with new questions
            </Button>
          </div>
          <div className="mt-6 space-y-2.5">
            {r.areas.map((a) => (
              <div key={a.key} className="flex items-center gap-3 text-[13px]">
                <span className="w-40 shrink-0 truncate sm:w-52" title={a.name}>{a.name}</span>
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-secondary">
                  <div className={cn("h-full rounded-full", a.correct === a.total ? "bg-success" : a.correct ? "bg-primary" : "bg-warning")}
                    style={{ width: `${Math.max(4, (a.correct / a.total) * 100)}%` }} />
                </div>
                <span className="w-10 shrink-0 text-right tabular-nums text-muted-foreground">{a.correct}/{a.total}</span>
                {a.correct < a.total ? (
                  <span className="flex shrink-0 gap-1">
                    <Button size="sm" variant="ghost" title={`Tour ${a.name}`} onClick={() => onTour(a.name)}><Route className="size-3.5" /><span className="sr-only sm:not-sr-only">Tour it</span></Button>
                    <Button size="sm" variant="ghost" title={`Ask about ${a.name}`} onClick={() => onAsk(`Explain how ${a.name} works in this codebase, for someone new to it.`)}><MessageSquare className="size-3.5" /><span className="sr-only sm:not-sr-only">Ask</span></Button>
                  </span>
                ) : <span className="w-[7.5rem] shrink-0 max-sm:hidden" />}
              </div>
            ))}
          </div>
        </FadeIn>

        <FadeIn delay={0.05}>
          <SectionLabel>Review</SectionLabel>
          <div className="space-y-3">
            {r.results.map((x) => (
              <article key={x.n} className={cn("rounded-xl border bg-card p-4", x.correct ? "border-border" : "border-warning/50")}>
                <div className="flex items-start gap-2.5">
                  <span className={cn("mt-0.5 grid size-5 shrink-0 place-items-center rounded-full", x.correct ? "bg-success text-white" : "bg-warning text-white")}>
                    {x.correct ? <Check className="size-3.5" /> : <X className="size-3.5" />}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-[14px] font-medium"><Inline text={x.question} /></p>
                    <ul className="mt-2 space-y-1 text-[13px]">
                      {x.options.map((o, i) => (
                        <li key={i} className={cn("flex gap-2", i === x.answer ? "font-medium text-success" : i === x.chosen ? "text-warning line-through" : "text-muted-foreground")}>
                          <span className="font-mono">{LETTERS[i]}</span>
                          <span className="min-w-0 break-words"><Inline text={o} /></span>
                          {i === x.chosen && <span className="shrink-0 text-[11px] no-underline">(your answer)</span>}
                        </li>
                      ))}
                    </ul>
                    {x.chosen == null && <p className="mt-1 text-[12px] text-warning">Not answered</p>}
                    <Markdown text={x.explanation} className="mt-2 text-[13px] text-muted-foreground" />
                  </div>
                </div>
                <div className="mt-2 border-t border-border pt-1">
                  <CitationChip file={x.cite.file} start={x.cite.start_line} end={x.cite.end_line} variant="row" />
                </div>
              </article>
            ))}
          </div>
        </FadeIn>
        {attempts.length > 1 && <History attempts={attempts} />}
      </div>
    </div>
  );
}

function History({ attempts }: { attempts: QuizAttempt[] }) {
  return (
    <div className="w-full max-w-md text-left">
      <SectionLabel>Your past attempts</SectionLabel>
      <ul className="overflow-hidden rounded-lg border border-border bg-card text-[13px]">
        {attempts.map((a, i) => (
          <li key={a.id} className={cn("flex items-center gap-3 px-3 py-2 tabular-nums", i > 0 && "border-t border-border")}>
            <span className="w-24 shrink-0 text-muted-foreground">{new Date(a.at * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</span>
            <span className="flex-1 font-medium">{a.correct}/{a.total}</span>
            <span className="text-muted-foreground">{Math.round(a.total ? (a.correct / a.total) * 100 : 0)}%</span>
            <span className="w-14 text-right text-muted-foreground">{Math.max(1, Math.round(a.seconds / 60))} min</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
