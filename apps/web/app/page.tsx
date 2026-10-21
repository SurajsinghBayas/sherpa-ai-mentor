import Link from "next/link";
import { ArrowRight, FileCode2, FolderUp, Github, ShieldCheck, Terminal } from "lucide-react";
import { Sherpa, SherpaAvatar, SherpaSays, Wordmark, type Pose } from "../components/sherpa";
import { buttonVariants } from "../components/ui/button-variants";
import { AdFilm } from "../components/ad-film";
import { cn } from "../lib/utils";

const STEPS: { pose: Pose; title: string; body: string }[] = [
  {
    pose: "exploring",
    title: "Bring the code",
    body: "Paste a GitHub URL, drop a ZIP, pick a local folder or run one CLI command. Dependencies, build output and secrets are left out.",
  },
  {
    pose: "analyzing",
    title: "Sherpa maps it",
    body: "Files are chunked and embedded, entry points found and the main parts of the system connected into a map.",
  },
  {
    pose: "explaining",
    title: "Ask and follow along",
    body: "Ask how something works, or take a tour through a flow. Every answer points to the file and line it came from.",
  },
];

const FEATURES: { pose: Pose; title: string; body: string }[] = [
  { pose: "explaining", title: "Answers with sources", body: "Plain-English answers to how and why questions, each claim linked to the lines that support it." },
  { pose: "analyzing", title: "Architecture map", body: "The main components, what each one does and how they import each other, drawn as a diagram." },
  { pose: "exploring", title: "Guided tours", body: "Walk a flow such as signup or checkout stop by stop, with the code shown at every step." },
  { pose: "coding", title: "Starter tasks", body: "First-contribution-sized tasks taken from the real code, with the files to touch and the steps." },
  { pose: "guide", title: "Living docs", body: "An onboarding guide written from the code. When files change, only the sections that cite them are rewritten." },
  { pose: "success", title: "Checked citations", body: "A verifier confirms each file:line exists in the indexed snapshot and removes any that don't." },
];

const SOURCES = [
  { icon: Github, label: "GitHub URL" },
  { icon: FolderUp, label: "ZIP or folder" },
  { icon: Terminal, label: "sherpa CLI" },
];

function ProductPreview() {
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card shadow-pop">
      <div className="flex items-center gap-2 border-b border-border px-4 py-2.5">
        <span className="flex gap-1.5" aria-hidden>
          <span className="size-2.5 rounded-full bg-border" />
          <span className="size-2.5 rounded-full bg-border" />
          <span className="size-2.5 rounded-full bg-border" />
        </span>
        <span className="ml-2 truncate font-mono text-xs text-muted-foreground">fastapi/full-stack-fastapi-template</span>
        <span className="ml-auto hidden items-center gap-1 text-[11px] text-success sm:flex">
          <ShieldCheck className="size-3.5" /> 2 verified sources
        </span>
      </div>

      <div className="space-y-4 p-4 sm:p-5">
        <div className="ml-auto w-fit max-w-[85%] rounded-lg bg-foreground px-3.5 py-2.5 text-sm text-background">
          What happens when a user signs up?
        </div>
        <div className="flex gap-3">
          <SherpaAvatar />
          <div className="min-w-0 flex-1 space-y-3 text-sm leading-relaxed">
            <p>
              The form validates input and calls <code>signUpMutation</code>, which posts to <code>register_user</code>. The
              endpoint rejects duplicate emails, creates the user through <code>crud.create_user</code>, and the UI then
              redirects to <code>/login</code>.
            </p>
            <div className="flex flex-wrap gap-1.5">
              {["frontend/src/hooks/useAuth.ts:29-39", "backend/app/api/routes/users.py:147-159"].map((s) => (
                <span
                  key={s}
                  className="inline-flex items-center gap-1 rounded-md border border-primary/25 bg-primary/[0.07] px-1.5 py-0.5 font-mono text-[11px] text-primary"
                >
                  <FileCode2 className="size-3" />
                  {s}
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* the cited code, as it appears when a citation is opened */}
        <div className="overflow-hidden rounded-lg bg-code font-mono text-[11.5px] leading-[1.7] text-code-foreground">
          <div className="border-b border-white/5 px-3 py-1.5 text-[11px] text-code-muted">backend/app/api/routes/users.py</div>
          <pre className="scroll-thin-code overflow-x-auto py-2">
            {[
              [147, '@router.post("/signup", response_model=UserPublic)'],
              [148, "def register_user(session: SessionDep, user_in: UserRegister):"],
              [149, "    user = crud.get_user_by_email(session=session, email=user_in.email)"],
              [150, "    if user:"],
              [151, '        raise HTTPException(400, "The user with this email already exists")'],
            ].map(([n, line]) => (
              <div key={n} className={cn("flex min-w-max pr-4", Number(n) >= 148 && Number(n) <= 151 && "bg-code-line/15")}>
                <span className="w-10 shrink-0 select-none pr-3 text-right text-code-muted">{n}</span>
                <span className="whitespace-pre">{line}</span>
              </div>
            ))}
          </pre>
        </div>
      </div>
    </div>
  );
}

export default function Landing() {
  return (
    <main>
      {/* Hero */}
      <section className="container grid items-center gap-12 py-14 sm:py-20 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)] lg:gap-16">
        <div className="animate-enter-up">
          <SherpaSays pose="happy" size={64} className="max-w-sm">
            Hi! I&apos;m Sherpa. I&apos;ll help you find your way around a new codebase.
          </SherpaSays>

          <p className="eyebrow mt-10">Codebase mentor</p>
          <h1 className="mt-3 text-[2.6rem] font-semibold leading-[1.05] sm:text-6xl">
            Your codebase,
            <br />
            <span className="text-primary">explained.</span>
          </h1>
          <p className="mt-5 max-w-lg text-[17px] leading-relaxed text-muted-foreground">
            Sherpa reads a repository and walks you through it: answers, maps and tours that cite the exact file and line
            they come from, so you can check every claim.
          </p>

          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link href="/signup" className={buttonVariants({ variant: "ink", size: "xl" })}>
              Get started <ArrowRight />
            </Link>
            <Link href="/login" className={buttonVariants({ variant: "outline", size: "xl" })}>
              Sign in
            </Link>
          </div>

          <ul className="mt-8 flex flex-wrap items-center gap-x-5 gap-y-2 text-[13px] text-muted-foreground">
            {SOURCES.map(({ icon: Icon, label }) => (
              <li key={label} className="flex items-center gap-1.5">
                <Icon className="size-4" /> {label}
              </li>
            ))}
          </ul>
        </div>

        <div className="animate-enter-up [animation-delay:80ms]">
          <ProductPreview />
        </div>
      </section>

      {/* The film */}
      <section className="border-t border-border">
        <div className="container py-20">
          <div className="mx-auto max-w-2xl text-center">
            <p className="eyebrow">See it in action</p>
            <h2 className="mt-3 text-3xl font-semibold sm:text-4xl">Thirty seconds with Sherpa</h2>
            <p className="mt-4 text-muted-foreground">
              A new joiner, a codebase they have never seen, and Sherpa showing them around.
            </p>
          </div>
          <AdFilm className="mx-auto mt-12 max-w-5xl" />
        </div>
      </section>

      {/* How it works */}
      <section className="border-t border-border bg-card">
        <div className="container py-20">
          <p className="eyebrow">How it works</p>
          <h2 className="mt-3 max-w-xl text-3xl font-semibold sm:text-4xl">From a repository to a guided tour in minutes</h2>
          <ol className="mt-12 grid gap-px overflow-hidden rounded-xl border border-border bg-border md:grid-cols-3">
            {STEPS.map((s, i) => (
              <li key={s.title} className="flex flex-col bg-card p-6">
                <div className="flex items-start justify-between">
                  <Sherpa pose={s.pose} size={80} animated={false} />
                  <span className="font-mono text-xs text-muted-foreground">0{i + 1}</span>
                </div>
                <h3 className="mt-5 font-semibold">{s.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{s.body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* Features */}
      <section className="border-t border-border">
        <div className="container py-20">
          <div className="grid gap-10 lg:grid-cols-[minmax(0,20rem)_1fr]">
            <div>
              <p className="eyebrow">What Sherpa does</p>
              <h2 className="mt-3 text-3xl font-semibold sm:text-4xl">Everything a new engineer asks in week one</h2>
              <p className="mt-4 text-muted-foreground">
                Sherpa is built for the questions you would otherwise ask a busy teammate, and it never answers without
                showing where the answer came from.
              </p>
            </div>
            <ul className="grid gap-px overflow-hidden rounded-xl border border-border bg-border sm:grid-cols-2">
              {FEATURES.map((f) => (
                <li key={f.title} className="flex gap-4 bg-card p-5">
                  <Sherpa pose={f.pose} size={48} animated={false} decorative />
                  <div className="min-w-0">
                    <h3 className="text-[15px] font-semibold">{f.title}</h3>
                    <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{f.body}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* CTA, on the navy card from the logo sheet */}
      <section className="container pb-20">
        <div className="flex flex-col items-center gap-8 rounded-2xl bg-navy px-6 py-12 text-cream sm:flex-row sm:px-12">
          <Sherpa pose="guide" size={128} />
          <div className="flex-1 text-center sm:text-left">
            <p className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-sky-brand">Navigate any codebase</p>
            <h2 className="mt-3 text-3xl font-semibold">Understand. Explore. Build.</h2>
            <p className="mt-3 max-w-md text-cream/70">
              Index your first repository and ask a question. It takes about a minute for a mid-sized project.
            </p>
          </div>
          <Link
            href="/signup"
            className={cn(buttonVariants({ size: "xl" }), "bg-cream text-navy hover:bg-cream/90")}
          >
            Create a free account <ArrowRight />
          </Link>
        </div>
      </section>

      <footer className="border-t border-border">
        <div className="container flex flex-col items-center justify-between gap-4 py-8 sm:flex-row">
          <div className="flex items-center gap-3">
            <Wordmark size={22} />
            <span className="text-sm text-muted-foreground">Your AI guide for any codebase.</span>
          </div>
          <nav aria-label="Footer" className="flex items-center gap-5 text-sm text-muted-foreground">
            <Link href="/cli" className="transition-colors hover:text-foreground">CLI</Link>
            <Link href="/login" className="transition-colors hover:text-foreground">Sign in</Link>
            <Link href="/signup" className="transition-colors hover:text-foreground">Sign up</Link>
          </nav>
        </div>
      </footer>
    </main>
  );
}
