"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight, FileSearch, KeyRound, Map, Route, ShieldCheck, Sparkles } from "lucide-react";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/primitives";

const rise = {
  hidden: { opacity: 0, y: 16 },
  show: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.55, delay: i * 0.08, ease: [0.22, 1, 0.36, 1] as const },
  }),
};

const FEATURES = [
  { icon: FileSearch, title: "Grounded Q&A", body: "Every answer cites the exact file:line it came from. Unverifiable claims are withheld, not hallucinated." },
  { icon: Map, title: "Architecture maps", body: "Components, roles, and import edges rendered as a mermaid graph — the map before the maze." },
  { icon: Route, title: "Guided tours", body: "Follow signup → handler → service → model step by step, with the code inline at each stop." },
  { icon: Sparkles, title: "Starter tasks", body: "First-PR-sized tasks generated from the actual repo, with files and steps attached." },
  { icon: KeyRound, title: "Bring your own keys", body: "Add OpenAI, Anthropic, Gemini keys or any OpenAI-compatible endpoint. Encrypted at rest, last4 only in UI." },
  { icon: ShieldCheck, title: "JWT + Postgres", body: "Real multi-user auth, Neon Postgres in prod, SQLite zero-setup fallback for local demos." },
];

export default function Landing() {
  return (
    <main>
      {/* hero */}
      <section className="container flex flex-col items-center py-20 text-center sm:py-28">
        <motion.div variants={rise} initial="hidden" animate="show" custom={0}>
          <span className="inline-flex items-center gap-1.5 rounded-full border bg-secondary px-3 py-1 text-xs font-medium text-secondary-foreground">
            <Sparkles className="size-3" /> Agentic onboarding for developers
          </span>
        </motion.div>
        <motion.h1
          variants={rise} initial="hidden" animate="show" custom={1}
          className="mt-6 max-w-3xl text-4xl font-semibold leading-[1.1] tracking-tight sm:text-6xl"
        >
          Understand any codebase in hours, not weeks.
        </motion.h1>
        <motion.p variants={rise} initial="hidden" animate="show" custom={2} className="mt-5 max-w-xl text-lg text-muted-foreground">
          Sherpa reads the repository and mentors newcomers with answers grounded in the actual code — every claim clickable to its source.
        </motion.p>
        <motion.div variants={rise} initial="hidden" animate="show" custom={3} className="mt-8 flex gap-3">
          <Link href="/signup"><Button size="lg">Start onboarding <ArrowRight /></Button></Link>
          <Link href="/login"><Button size="lg" variant="outline">Sign in</Button></Link>
        </motion.div>
        <motion.div variants={rise} initial="hidden" animate="show" custom={4} className="mt-10 w-full max-w-2xl">
          <Card className="animate-scale-in text-left">
            <CardContent className="pt-6">
              <p className="font-mono text-xs text-muted-foreground">$ curl sherpa/api/ask</p>
              <p className="mt-2 text-sm">“How does user signup work?”</p>
              <div className="mt-3 space-y-1.5 font-mono text-xs">
                <div className="rounded-md bg-secondary px-3 py-2">app/auth.py:5-9 — POST /signup handler</div>
                <div className="rounded-md bg-secondary px-3 py-2">app/users.py:41-58 — create_user + hashing</div>
                <div className="rounded-md bg-secondary px-3 py-2">app/models.py:12-20 — User schema</div>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      </section>

      {/* features */}
      <section className="container grid gap-4 pb-24 sm:grid-cols-2 lg:grid-cols-3">
        {FEATURES.map((f, i) => (
          <motion.div key={f.title} variants={rise} initial="hidden" whileInView="show" viewport={{ once: true }} custom={i}>
            <Card className="h-full transition-transform duration-300 ease-out hover:-translate-y-1">
              <CardHeader>
                <span className="flex size-9 items-center justify-center rounded-lg bg-secondary text-foreground">
                  <f.icon className="size-4" />
                </span>
                <CardTitle className="pt-2">{f.title}</CardTitle>
                <CardDescription>{f.body}</CardDescription>
              </CardHeader>
            </Card>
          </motion.div>
        ))}
      </section>
    </main>
  );
}
