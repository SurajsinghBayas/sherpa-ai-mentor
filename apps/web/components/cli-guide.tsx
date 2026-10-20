"use client";

import Link from "next/link";
import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { API } from "../lib/api";
import { useAuth } from "../lib/auth";
import { cn } from "../lib/utils";
import { Sherpa } from "./sherpa";
import { Tabs } from "./ui/primitives";

type OS = "unix" | "windows";

/** One copyable shell command (or a few lines). `$ ` prompts are shown but never copied. */
export function CopyCommand({ code, className }: { code: string; className?: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked (insecure origin): the text is still selectable */
    }
  }
  return (
    <div className={cn("group relative rounded-lg bg-code", className)}>
      <pre className="py-2.5 pl-3 pr-10 font-mono text-[12px] leading-[1.65] text-code-foreground">
        {code.split("\n").map((ln, i) => (
          // long commands wrap instead of running under the copy button (copying is unaffected)
          <div key={i} className="whitespace-pre-wrap break-all pl-3.5 -indent-3.5">
            {ln.startsWith("#") ? (
              <span className="text-code-muted">{ln}</span>
            ) : (
              <>
                <span className="select-none text-code-muted">$ </span>
                {ln}
              </>
            )}
          </div>
        ))}
      </pre>
      <button
        onClick={copy}
        aria-label="Copy command"
        title="Copy"
        className="absolute right-1.5 top-1.5 rounded-md p-1.5 text-code-muted opacity-80 transition-[opacity,background-color,color] duration-150 hover:bg-white/10 hover:text-code-foreground group-hover:opacity-100"
      >
        {copied ? <Check className="size-3.5 text-sky-brand" /> : <Copy className="size-3.5" />}
      </button>
    </div>
  );
}

function commands(os: OS, email?: string) {
  const unix = os === "unix";
  const sherpa = unix ? "sherpa" : "python sherpa.py";
  return {
    sherpa,
    install: unix
      ? `mkdir -p ~/.local/bin && curl -fsSL ${API}/cli/sherpa.py -o ~/.local/bin/sherpa && chmod +x ~/.local/bin/sherpa`
      : `curl.exe -fsSL ${API}/cli/sherpa.py -o sherpa.py`,
    login: `${sherpa} login${email ? ` --email ${email}` : ""}`,
    upload: `cd path/to/your-project\n${sherpa} upload`,
    ask: `${sherpa} repos\n${sherpa} ask <repo_id> "How does signup work?"`,
  };
}

function OsSwitch({ os, setOs }: { os: OS; setOs: (o: OS) => void }) {
  return (
    <Tabs
      label="Operating system"
      value={os}
      onValueChange={(v) => setOs(v as OS)}
      tabs={[
        { value: "unix", label: "macOS / Linux" },
        { value: "windows", label: "Windows" },
      ]}
    />
  );
}

function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-3">
      <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-md bg-secondary text-[11px] font-semibold tabular-nums">{n}</span>
      <div className="min-w-0 flex-1 space-y-1.5">
        <p className="text-xs font-medium">{title}</p>
        {children}
      </div>
    </div>
  );
}

/** Compact version for the "Add repo" panel. */
export function CliQuickstart() {
  const { user } = useAuth();
  const [os, setOs] = useState<OS>(() =>
    typeof navigator !== "undefined" && /Win/i.test(navigator.platform) ? "windows" : "unix"
  );
  const c = commands(os, user?.email);
  return (
    <div className="mt-3 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[11px] text-muted-foreground">Upload from your terminal. Needs Python 3.9+; nothing else to install.</p>
        <OsSwitch os={os} setOs={setOs} />
      </div>
      <Step n={1} title="Install">
        <CopyCommand code={c.install} />
      </Step>
      <Step n={2} title="Sign in (we email you a code)">
        <CopyCommand code={c.login} />
      </Step>
      <Step n={3} title="Upload a project">
        <CopyCommand code={c.upload} />
      </Step>
      <p className="text-[11px] text-muted-foreground">
        Uploads from the CLI appear here while they index.{" "}
        <Link href="/cli" className="font-medium text-foreground underline-offset-4 hover:underline">
          Full CLI guide →
        </Link>
      </p>
    </div>
  );
}

function H2({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <h2 id={id} className="scroll-mt-20 pt-6 text-lg font-semibold">
      {children}
    </h2>
  );
}

function P({ children }: { children: React.ReactNode }) {
  return <p className="text-sm leading-relaxed text-muted-foreground">{children}</p>;
}

function Code({ children }: { children: React.ReactNode }) {
  return <code className="rounded bg-secondary px-1 py-0.5 font-mono text-[12px] text-foreground">{children}</code>;
}

function Table({ head, rows }: { head: [string, string]; rows: [React.ReactNode, React.ReactNode][] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-card">
      <table className="w-full text-left text-sm">
        <thead className="eyebrow bg-secondary/60">
          <tr>
            <th className="px-3 py-2 font-medium">{head[0]}</th>
            <th className="px-3 py-2 font-medium">{head[1]}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([a, b], i) => (
            <tr key={i} className="border-t border-border align-top">
              <td className="whitespace-nowrap px-3 py-2 font-mono text-[12px]">{a}</td>
              <td className="px-3 py-2 text-muted-foreground">{b}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const TOC = [
  ["install", "Install"], ["login", "Sign in"], ["upload", "Upload a project"], ["update", "Update a project"],
  ["ask", "Ask questions"], ["status", "Status & retry"], ["reference", "Commands"], ["ci", "Use in CI"],
  ["limits", "Limits"], ["troubleshooting", "Troubleshooting"],
] as const;

/** The full guide (also in cli/README.md). Commands are filled in for this server. */
export function CliGuide() {
  const { user } = useAuth();
  const [os, setOs] = useState<OS>("unix");
  const c = commands(os, user?.email);
  const s = c.sherpa;
  return (
    <main className="container max-w-5xl py-10">
      <div className="flex items-center gap-4">
        <Sherpa pose="coding" size={80} decorative />
        <div>
          <p className="eyebrow">Command-line tool</p>
          <h1 className="mt-1 text-3xl font-semibold">Sherpa CLI</h1>
          <p className="mt-1 text-sm text-muted-foreground">Upload a codebase from your machine and ask about it, from the terminal.</p>
        </div>
      </div>

      <div className="mt-8 grid gap-10 lg:grid-cols-[180px_1fr]">
        <nav className="hidden lg:block">
          <div className="sticky top-20 space-y-1 text-sm">
            {TOC.map(([id, label]) => (
              <a key={id} href={`#${id}`} className="block rounded-md px-2 py-1 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground">
                {label}
              </a>
            ))}
          </div>
        </nav>

        <article className="min-w-0 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card p-4 shadow-card">
            <P>
              One Python file, no dependencies (Python 3.9+). Uploads show up in your dashboard like any other project.
              The commands below are set up for <Code>{API}</Code>.
            </P>
            <OsSwitch os={os} setOs={setOs} />
          </div>

          <H2 id="install">Install</H2>
          <CopyCommand code={c.install} />
          {os === "unix" ? (
            <P>
              If your shell then says <Code>sherpa: command not found</Code>, add <Code>~/.local/bin</Code> to your PATH:{" "}
              <Code>export PATH=&quot;$HOME/.local/bin:$PATH&quot;</Code> (put it in <Code>~/.zshrc</Code> or <Code>~/.bashrc</Code>).
            </P>
          ) : (
            <P>
              Run it from the folder you saved it to, as <Code>python sherpa.py …</Code> (use <Code>py</Code> if <Code>python</Code> isn&apos;t found).
            </P>
          )}
          <CopyCommand code={`${s} --version`} />

          <H2 id="login">Sign in</H2>
          <CopyCommand code={c.login} />
          <P>
            We email you a 6-digit code; type it in. This works for every account, including ones created with Google. Password account?
            Add <Code>--password</Code>. The session is saved in <Code>~/.config/sherpa/config.json</Code> (readable only by you) and lasts a day.
          </P>
          <CopyCommand code={`${s} whoami\n${s} logout`} />

          <H2 id="upload">Upload a project</H2>
          <CopyCommand code={c.upload} />
          <P>What happens:</P>
          <ol className="list-decimal space-y-1.5 pl-5 text-sm text-muted-foreground">
            <li>
              <span className="text-foreground">Packing.</span> In a git checkout only files git tracks are sent, so <Code>.gitignore</Code> is
              respected. Dependencies and build output (<Code>node_modules/</Code>, <Code>.git/</Code>, <Code>dist/</Code>, <Code>build/</Code>,{" "}
              <Code>vendor/</Code> …), lockfiles, binaries, files over 400 KB, <Code>.env</Code> files and private keys are always left out.
            </li>
            <li><span className="text-foreground">Uploading</span> the zipped files (100 MB limit).</li>
            <li>
              <span className="text-foreground">Review.</span> You see the project type, file count, size, languages and entry points, and
              confirm with <Code>Y</Code> before anything is indexed.
            </li>
            <li><span className="text-foreground">Indexing</span> with a progress bar; it prints the repo id when ready.</li>
          </ol>
          <Table
            head={["Option", "What it does"]}
            rows={[
              ["PATH", "Folder to upload. Default: the current folder."],
              ["--name NAME", "Project name. Default: the folder's name."],
              ["-y, --yes", "Skip the confirmation (for scripts and CI)."],
              ["--no-wait", "Return as soon as indexing starts; check later with status."],
            ]}
          />

          <H2 id="update">Update a project</H2>
          <P>Upload again with the same name. Only changed files are re-indexed, so it&apos;s much faster than the first time.</P>
          <CopyCommand code={`${s} upload --name my-project -y`} />

          <H2 id="ask">Ask questions</H2>
          <CopyCommand code={c.ask} />
          <P>Answers are printed as Markdown, followed by the exact file and line ranges they are based on.</P>

          <H2 id="status">Status &amp; retry</H2>
          <CopyCommand code={`${s} status\n${s} retry <job_id>`} />
          <P>A failed upload can be retried for 24 hours without uploading the files again.</P>

          <H2 id="reference">Commands</H2>
          <Table
            head={["Command", "Purpose"]}
            rows={[
              [`${s} login [--email E] [--password]`, "Sign in and save the session"],
              [`${s} logout · whoami`, "Forget the session · show the account and server"],
              [`${s} upload [PATH] [--name N] [-y] [--no-wait]`, "Upload, review and index a folder"],
              [`${s} status`, "Your 20 most recent uploads"],
              [`${s} retry JOB_ID`, "Retry a failed upload without re-uploading"],
              [`${s} repos`, "Your projects and their ids"],
              [`${s} ask REPO_ID "QUESTION"`, "A cited answer"],
              [`${s} COMMAND --help`, "Help for one command"],
            ]}
          />

          <H2 id="ci">Use in CI</H2>
          <P>
            Keep the index in step with your code by uploading on every push. Set <Code>SHERPA_TOKEN</Code> (from a{" "}
            <Code>login</Code>, stored as a CI secret) instead of signing in. Tokens expire after a day by default.
          </P>
          <CopyCommand
            code={`# with SHERPA_TOKEN set from your CI secrets\ncurl -fsSL ${API}/cli/sherpa.py -o sherpa.py\npython3 sherpa.py upload . --name my-project --yes`}
          />

          <H2 id="limits">Limits</H2>
          <Table
            head={["Limit", "Value"]}
            rows={[
              ["Upload size", "100 MB packed"],
              ["Indexed per project", "50 MB of text, up to 1,500 files; single files up to 400 KB"],
              ["At once", "1 upload indexing per account"],
              ["Projects", "15 per account"],
              ["Imports per day", "30 (uploads, re-uploads and retries each count)"],
            ]}
          />

          <H2 id="troubleshooting">Troubleshooting</H2>
          <Table
            head={["Message", "What to do"]}
            rows={[
              ["can't reach the Sherpa API", <>Check the server with <Code>{s} whoami</Code>; reinstall from this page to reset it.</>],
              ["not signed in / session expired", <>Run <Code>{s} login</Code>.</>],
              ["no account with this email", "Sign up in the web app first."],
              ["the packed project is … MB", <>Upload a subfolder, or add generated files to <Code>.gitignore</Code>.</>],
              ["no source files to upload", "Everything was filtered out; check you're in the right folder."],
              ["another upload is still indexing", <>Wait for it (<Code>{s} status</Code>), then retry.</>],
              ["daily ingest limit / repo limit reached", "Try again tomorrow (UTC), or delete a project in the dashboard."],
            ]}
          />
        </article>
      </div>
    </main>
  );
}
