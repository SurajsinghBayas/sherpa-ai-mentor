"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import {
  ArrowRight,
  BookOpen,
  CheckCircle2,
  ChevronRight,
  FileCode2,
  GitBranch,
  KeyRound,
  ListTodo,
  Map,
  MessageSquare,
  Route,
  Shield,
  Sparkles,
  Zap,
} from "lucide-react";
import { SherpaOrb, SherpaAvatar } from "../components/sherpa-orb";
import { Button, Badge } from "../components/ui/primitives";

const ease = [0.22, 1, 0.36, 1] as const;

function rise(i: number) {
  return {
    initial: { opacity: 0, y: 18 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.6, delay: i * 0.09, ease },
  };
}

function inView(i: number) {
  return {
    initial: { opacity: 0, y: 20 },
    whileInView: { opacity: 1, y: 0 },
    viewport: { once: true, margin: "-40px" },
    transition: { duration: 0.55, delay: i * 0.07, ease },
  };
}

const DEMO_EXCHANGE = [
  {
    role: "user" as const,
    text: "How does user authentication work?",
  },
  {
    role: "sherpa" as const,
    text: "Auth flows through POST /api/auth/login. The handler validates credentials with bcrypt, then issues a 24-hour JWT signed with your configured secret.",
    sources: ["app/routers/auth.py:38-44", "app/security.py:22-33"],
  },
];

const FEATURES = [
  {
    icon: MessageSquare,
    title: "Grounded Q&A",
    body: "Every answer cites the exact file:line it came from. Unverifiable claims are dropped — never hallucinated.",
    color: "text-blue-400",
    bg: "bg-blue-500/8",
  },
  {
    icon: Map,
    title: "Architecture maps",
    body: "Components, roles, and import edges rendered as a Mermaid graph — the map before the maze.",
    color: "text-violet-400",
    bg: "bg-violet-500/8",
  },
  {
    icon: Route,
    title: "Guided tours",
    body: "Follow signup → handler → service → model step by step, with code inline at every stop.",
    color: "text-emerald-400",
    bg: "bg-emerald-500/8",
  },
  {
    icon: ListTodo,
    title: "Starter tasks",
    body: "First-PR-sized tasks generated from the actual repo, with files and steps attached.",
    color: "text-amber-400",
    bg: "bg-amber-500/8",
  },
  {
    icon: KeyRound,
    title: "Bring your own keys",
    body: "OpenAI, Anthropic, Gemini, or any OpenAI-compatible endpoint — encrypted at rest, last 4 digits shown in UI.",
    color: "text-rose-400",
    bg: "bg-rose-500/8",
  },
  {
    icon: Shield,
    title: "Grounding verifier",
    body: "A citation verifier parses every file:line claim, checks it exists in the snapshot, and drops ghosts.",
    color: "text-cyan-400",
    bg: "bg-cyan-500/8",
  },
];

const HOW_IT_WORKS = [
  {
    step: "01",
    icon: GitBranch,
    title: "Index any repo",
    body: "Paste a GitHub URL. Sherpa clones, walks, and chunks the code into a semantic index in seconds.",
  },
  {
    step: "02",
    icon: MessageSquare,
    title: "Ask anything",
    body: "Ask questions in plain English. Sherpa retrieves relevant chunks, reasons over them, and writes a grounded answer.",
  },
  {
    step: "03",
    icon: CheckCircle2,
    title: "Get verified answers",
    body: "Every claim is verified against the actual snapshot. Citations link you straight to the source code.",
  },
];

const STATS = [
  { value: "< 30s", label: "to index any repo" },
  { value: "100%", label: "of answers are grounded" },
  { value: "file:line", label: "precision on every cite" },
  { value: "0 setup", label: "needed to start" },
];

export default function Landing() {
  return (
    <main className="overflow-hidden">
      {/* ── Hero ─────────────────────────────────────────────────────── */}
      <section className="relative min-h-[90vh] flex flex-col items-center justify-center px-4 text-center">
        {/* background grid + radial glow */}
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.025] dark:opacity-[0.04]"
          style={{
            backgroundImage:
              "linear-gradient(hsl(var(--border)) 1px, transparent 1px), linear-gradient(90deg, hsl(var(--border)) 1px, transparent 1px)",
            backgroundSize: "48px 48px",
          }}
        />
        <div className="pointer-events-none absolute inset-0 hero-glow" />

        {/* orb */}
        <motion.div {...rise(0)} className="mb-8">
          <SherpaOrb size="xl" state="idle" />
        </motion.div>

        {/* badge */}
        <motion.div {...rise(1)} className="mb-6">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-secondary px-3 py-1 text-xs font-medium text-muted-foreground">
            <Sparkles className="size-3 text-sherpa-glow" />
            Agentic onboarding for developers
          </span>
        </motion.div>

        {/* headline */}
        <motion.h1
          {...rise(2)}
          className="max-w-3xl text-5xl font-semibold tracking-tight leading-[1.08] sm:text-7xl"
        >
          Understand any codebase,
          <br />
          <span className="text-muted-foreground">immediately.</span>
        </motion.h1>

        {/* subheadline */}
        <motion.p
          {...rise(3)}
          className="mt-6 max-w-xl text-lg text-muted-foreground leading-relaxed"
        >
          Sherpa reads your repository and guides you with answers grounded in the
          actual code — every claim clickable to its source.
        </motion.p>

        {/* CTAs */}
        <motion.div {...rise(4)} className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <Link href="/signup">
            <Button size="lg" className="gap-2">
              Start onboarding <ArrowRight className="size-4" />
            </Button>
          </Link>
          <Link href="/login">
            <Button size="lg" variant="outline" className="gap-2">
              Sign in
            </Button>
          </Link>
        </motion.div>

        {/* demo chat card */}
        <motion.div
          {...rise(5)}
          className="mt-14 w-full max-w-xl"
        >
          <div className="rounded-2xl border border-border bg-card shadow-card overflow-hidden">
            {/* window chrome */}
            <div className="flex items-center gap-1.5 border-b border-border bg-secondary/40 px-4 py-3">
              <span className="h-2.5 w-2.5 rounded-full bg-border" />
              <span className="h-2.5 w-2.5 rounded-full bg-border" />
              <span className="h-2.5 w-2.5 rounded-full bg-border" />
              <span className="ml-3 text-xs text-muted-foreground font-mono">
                gothinkster/realworld
              </span>
            </div>

            <div className="space-y-3 p-4">
              {DEMO_EXCHANGE.map((msg, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 1.2 + i * 0.4, duration: 0.4, ease }}
                >
                  {msg.role === "user" ? (
                    <div className="flex justify-end">
                      <div className="message-user">{msg.text}</div>
                    </div>
                  ) : (
                    <div className="flex items-start gap-2.5">
                      <SherpaAvatar state="idle" />
                      <div className="message-sherpa !ml-0">
                        <p className="leading-relaxed">{msg.text}</p>
                        {msg.sources && (
                          <div className="mt-2 flex flex-wrap gap-1.5">
                            {msg.sources.map((s) => (
                              <span
                                key={s}
                                className="inline-flex items-center gap-1 rounded-md border border-border/60 bg-secondary/60 px-2 py-0.5 font-mono text-[10px] text-muted-foreground"
                              >
                                <FileCode2 className="size-2.5 shrink-0" />
                                {s}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </motion.div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* scroll hint */}
        <motion.div
          {...rise(6)}
          className="absolute bottom-8 left-1/2 -translate-x-1/2"
        >
          <motion.div
            animate={{ y: [0, 6, 0] }}
            transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
            className="flex h-8 w-5 items-start justify-center rounded-full border border-border pt-1.5"
          >
            <span className="block h-1.5 w-0.5 rounded-full bg-muted-foreground" />
          </motion.div>
        </motion.div>
      </section>

      {/* ── Stats strip ──────────────────────────────────────────────── */}
      <section className="border-y border-border bg-secondary/30">
        <div className="container grid grid-cols-2 divide-x divide-y divide-border sm:grid-cols-4 sm:divide-y-0">
          {STATS.map((s, i) => (
            <motion.div
              key={s.label}
              {...inView(i)}
              className="flex flex-col items-center justify-center gap-1 px-4 py-8"
            >
              <span className="text-3xl font-semibold tracking-tight">{s.value}</span>
              <span className="text-sm text-muted-foreground">{s.label}</span>
            </motion.div>
          ))}
        </div>
      </section>

      {/* ── How it works ─────────────────────────────────────────────── */}
      <section className="container py-24">
        <motion.div {...inView(0)} className="mb-12 text-center">
          <Badge variant="secondary" className="mb-4">How it works</Badge>
          <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">
            From repo URL to deep understanding
          </h2>
          <p className="mt-3 text-muted-foreground max-w-lg mx-auto">
            Three steps. No configuration. No setup. Works with any public GitHub repo.
          </p>
        </motion.div>

        <div className="grid gap-4 sm:grid-cols-3">
          {HOW_IT_WORKS.map((step, i) => (
            <motion.div
              key={step.step}
              {...inView(i + 1)}
              className="relative rounded-2xl border border-border bg-card p-6"
            >
              <div className="mb-4 flex items-center justify-between">
                <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-secondary">
                  <step.icon className="size-5 text-foreground" />
                </span>
                <span className="font-mono text-4xl font-semibold text-border">{step.step}</span>
              </div>
              <h3 className="font-semibold">{step.title}</h3>
              <p className="mt-2 text-sm text-muted-foreground leading-relaxed">{step.body}</p>

              {i < HOW_IT_WORKS.length - 1 && (
                <ChevronRight className="absolute -right-2.5 top-1/2 -translate-y-1/2 hidden h-5 w-5 text-border sm:block" />
              )}
            </motion.div>
          ))}
        </div>
      </section>

      {/* ── Features grid ────────────────────────────────────────────── */}
      <section className="container pb-24">
        <motion.div {...inView(0)} className="mb-12 text-center">
          <Badge variant="secondary" className="mb-4">Features</Badge>
          <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">
            Everything a new engineer needs
          </h2>
        </motion.div>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f, i) => (
            <motion.div
              key={f.title}
              {...inView(i)}
              whileHover={{ y: -3, transition: { duration: 0.2 } }}
              className="group rounded-2xl border border-border bg-card p-6 transition-shadow duration-300 hover:shadow-card-hover"
            >
              <span className={`mb-4 flex h-10 w-10 items-center justify-center rounded-xl ${f.bg}`}>
                <f.icon className={`size-5 ${f.color}`} />
              </span>
              <h3 className="font-semibold">{f.title}</h3>
              <p className="mt-2 text-sm text-muted-foreground leading-relaxed">{f.body}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* ── Agent section ────────────────────────────────────────────── */}
      <section className="relative overflow-hidden border-y border-border bg-secondary/20 py-24">
        <div className="container flex flex-col items-center gap-8 text-center lg:flex-row lg:text-left lg:gap-16">
          <motion.div {...inView(0)} className="flex justify-center lg:justify-start">
            <motion.div
              animate={{ y: [0, -8, 0] }}
              transition={{ duration: 5, repeat: Infinity, ease: "easeInOut" }}
            >
              <SherpaOrb size="xl" state="idle" />
            </motion.div>
          </motion.div>

          <div className="max-w-xl">
            <motion.div {...inView(0)}>
              <Badge variant="secondary" className="mb-4">
                <Sparkles className="size-3" /> Meet Sherpa
              </Badge>
            </motion.div>
            <motion.h2
              {...inView(1)}
              className="text-3xl font-semibold tracking-tight sm:text-4xl"
            >
              Your AI guide through any codebase
            </motion.h2>
            <motion.p
              {...inView(2)}
              className="mt-4 text-muted-foreground leading-relaxed"
            >
              Like having a senior engineer on call — except Sherpa has read every file,
              remembers every import, and never gets tired of your questions.
              Every answer is verified against the actual snapshot. No hallucinations.
              No "I think it might be" — only cites code that exists.
            </motion.p>

            <motion.div {...inView(3)} className="mt-6 flex flex-wrap gap-3">
              {[
                "Grounded citations",
                "Architecture maps",
                "Guided code tours",
                "Starter tasks",
                "BYOK models",
              ].map((tag) => (
                <span
                  key={tag}
                  className="inline-flex items-center gap-1 rounded-full border border-border bg-secondary px-3 py-1 text-xs font-medium"
                >
                  <CheckCircle2 className="size-3 text-emerald-500" />
                  {tag}
                </span>
              ))}
            </motion.div>

            <motion.div {...inView(4)} className="mt-8">
              <Link href="/signup">
                <Button size="lg">
                  Try Sherpa free <ArrowRight className="size-4" />
                </Button>
              </Link>
            </motion.div>
          </div>
        </div>
      </section>

      {/* ── CTA section ──────────────────────────────────────────────── */}
      <section className="container py-24 text-center">
        <motion.div {...inView(0)}>
          <SherpaOrb size="lg" state="idle" className="mx-auto mb-8" />
        </motion.div>
        <motion.h2
          {...inView(1)}
          className="text-4xl font-semibold tracking-tight sm:text-5xl"
        >
          Start with any repo.
        </motion.h2>
        <motion.p
          {...inView(2)}
          className="mt-4 text-lg text-muted-foreground max-w-md mx-auto"
        >
          No API key required to start. Index a public repo and ask your first question
          in under 30 seconds.
        </motion.p>
        <motion.div
          {...inView(3)}
          className="mt-8 flex flex-wrap items-center justify-center gap-3"
        >
          <Link href="/signup">
            <Button size="xl">
              Create free account <ArrowRight />
            </Button>
          </Link>
          <Link href="/dashboard">
            <Button size="xl" variant="outline">
              Try without signing in
            </Button>
          </Link>
        </motion.div>
      </section>

      {/* ── Footer ───────────────────────────────────────────────────── */}
      <footer className="border-t border-border">
        <div className="container flex flex-col items-center justify-between gap-4 py-8 sm:flex-row">
          <div className="flex items-center gap-2.5">
            <SherpaOrb size="xs" />
            <span className="text-sm font-medium">Sherpa</span>
            <span className="text-sm text-muted-foreground">— AI Codebase Mentor</span>
          </div>
          <div className="flex items-center gap-6 text-sm text-muted-foreground">
            <Link href="/dashboard" className="hover:text-foreground transition-colors">App</Link>
            <Link href="/signup" className="hover:text-foreground transition-colors">Sign up</Link>
            <Link href="/login" className="hover:text-foreground transition-colors">Sign in</Link>
          </div>
        </div>
      </footer>
    </main>
  );
}
