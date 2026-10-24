"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { useTheme } from "next-themes";
import { OTPInput, REGEXP_ONLY_DIGITS } from "input-otp";
import { ArrowLeft, ArrowRight, Eye, EyeOff, Github, Loader2, Mail } from "lucide-react";
import { API, api, ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import { isDesktop } from "../lib/desktop";
import { startGitHub } from "../lib/github-auth";
import { cn } from "../lib/utils";
import { Button, Input, Label } from "./ui/primitives";
import { Sherpa, type Pose } from "./sherpa";

type Mode = "login" | "signup";
type AuthConfig = { google_client_id: string | null; github?: boolean; email_otp: boolean; password: boolean };

function errorText(err: unknown, fallback: string) {
  return err instanceof ApiError ? err.message : fallback;
}

/** Shared sign-in completion: store the session and go to the workspace. */
function useFinish() {
  const { signIn } = useAuth();
  const router = useRouter();
  return async (token: string, message: string) => {
    await signIn(token);
    toast.success(message);
    router.push("/dashboard");
  };
}

function useAuthConfig() {
  const [cfg, setCfg] = useState<AuthConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    setError(null);
    // Google and GitHub only accept web origins they know; the desktop app (tauri://) signs in with an email code
    api
      .authConfig()
      .then((c) => setCfg(isDesktop() ? { ...c, google_client_id: null, github: false } : c))
      .catch((e) => {
        setCfg({ google_client_id: null, email_otp: true, password: true });
        setError(e instanceof ApiError ? e.message : `Can't reach the Sherpa API at ${API}`);
      });
  }, [attempt]);
  return { cfg, error, retry: () => setAttempt((n) => n + 1) };
}

function Working({ children }: { children: React.ReactNode }) {
  return (
    <span className="flex items-center gap-2">
      <Loader2 className="animate-spin" /> {children}
    </span>
  );
}

/** Six boxes for the emailed code; paste, autofill and the keyboard all work (input-otp). */
function CodeInput({ value, onChange, onComplete, disabled }: {
  value: string;
  onChange: (v: string) => void;
  onComplete: (v: string) => void;
  disabled?: boolean;
}) {
  return (
    <OTPInput
      id="code"
      maxLength={6}
      value={value}
      onChange={onChange}
      onComplete={onComplete}
      pattern={REGEXP_ONLY_DIGITS}
      inputMode="numeric"
      autoComplete="one-time-code"
      autoFocus
      disabled={disabled}
      containerClassName="flex items-center justify-between gap-2 has-[:disabled]:opacity-60"
      render={({ slots }) => (
        <>
          {slots.map((slot, i) => (
            <div
              key={i}
              className={cn(
                "relative flex h-12 flex-1 items-center justify-center rounded-lg border border-input bg-card font-mono text-xl font-medium tabular-nums",
                "transition-[border-color,box-shadow] duration-150",
                slot.isActive && "border-ring ring-[3px] ring-ring/20"
              )}
            >
              {slot.char ?? <span className="text-muted-foreground/40">·</span>}
              {slot.hasFakeCaret && <span className="absolute h-5 w-px animate-pulse bg-foreground" />}
            </div>
          ))}
        </>
      )}
    />
  );
}

function PasswordInput({
  id,
  value,
  onChange,
  placeholder,
  minLength,
  required,
}: React.InputHTMLAttributes<HTMLInputElement>) {
  const [show, setShow] = useState(false);
  return (
    <div className="relative">
      <Input
        id={id}
        type={show ? "text" : "password"}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        minLength={minLength}
        required={required}
        className="pr-10"
      />
      <button
        type="button"
        onClick={() => setShow((v) => !v)}
        aria-label={show ? "Hide password" : "Show password"}
        className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
      >
        {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
      </button>
    </div>
  );
}

/* ---------- Google ---------- */

type GoogleId = {
  initialize: (o: { client_id: string; callback: (r: { credential: string }) => void; ux_mode?: string }) => void;
  renderButton: (el: HTMLElement, o: Record<string, unknown>) => void;
};
declare global {
  interface Window {
    google?: { accounts: { id: GoogleId } };
  }
}

let gsiScript: Promise<void> | null = null;
export function loadGsi(): Promise<void> {
  if (window.google?.accounts?.id) return Promise.resolve();
  gsiScript ??= new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://accounts.google.com/gsi/client";
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => {
      gsiScript = null;
      reject(new Error("Google sign-in could not load"));
    };
    document.head.appendChild(s);
  });
  return gsiScript;
}

function GoogleButton({ clientId, mode, onBusy }: { clientId: string; mode: Mode; onBusy: (b: boolean) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const finish = useFinish();
  const [failed, setFailed] = useState(false);
  const { resolvedTheme } = useTheme();

  useEffect(() => {
    let cancelled = false;
    loadGsi()
      .then(() => {
        if (cancelled || !ref.current || !window.google) return;
        window.google.accounts.id.initialize({
          client_id: clientId,
          ux_mode: "popup",
          callback: async ({ credential }) => {
            onBusy(true);
            try {
              const { access_token } = await api.google(credential);
              await finish(access_token, mode === "signup" ? "Account ready — let's get started" : "Welcome back");
            } catch (err) {
              toast.error(errorText(err, "Google sign-in failed"));
            } finally {
              onBusy(false);
            }
          },
        });
        window.google.accounts.id.renderButton(ref.current, {
          theme: resolvedTheme === "dark" ? "filled_black" : "outline",
          size: "large",
          shape: "rectangular",
          text: mode === "signup" ? "signup_with" : "continue_with",
          width: Math.min(ref.current.offsetWidth || 320, 400),
        });
      })
      .catch(() => setFailed(true));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId, mode, resolvedTheme]);

  if (failed) {
    return <p className="text-center text-xs text-muted-foreground">Google sign-in couldn&apos;t load. Use an email code instead.</p>;
  }
  return <div ref={ref} className="flex min-h-[44px] w-full justify-center" />;
}

/* ---------- GitHub ---------- */

function GitHubButton({ mode, onBusy }: { mode: Mode; onBusy: (b: boolean) => void }) {
  const [going, setGoing] = useState(false);
  async function go() {
    setGoing(true);
    onBusy(true);
    try {
      await startGitHub(); // leaves the page for GitHub
    } catch (err) {
      toast.error(errorText(err, "GitHub sign-in is unavailable right now"));
      setGoing(false);
      onBusy(false);
    }
  }
  return (
    <Button variant="outline" size="lg" className="h-11 w-full" onClick={go} disabled={going}>
      {going ? <Loader2 className="animate-spin" /> : <Github />}
      {mode === "signup" ? "Sign up with GitHub" : "Continue with GitHub"}
    </Button>
  );
}

/* ---------- Email one-time code ---------- */

function EmailCodeForm({ mode, onBusy }: { mode: Mode; onBusy: (b: boolean) => void }) {
  const finish = useFinish();
  const [step, setStep] = useState<"email" | "code">("email");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [resendIn, setResendIn] = useState(0);

  useEffect(() => {
    if (resendIn <= 0) return;
    const t = setTimeout(() => setResendIn((s) => s - 1), 1000);
    return () => clearTimeout(t);
  }, [resendIn]);

  function working(b: boolean) {
    setBusy(b);
    onBusy(b);
  }

  async function send(e?: React.FormEvent) {
    e?.preventDefault();
    working(true);
    try {
      const r = await api.requestCode(email.trim(), mode, name.trim());
      setStep("code");
      setCode("");
      setResendIn(r.resend_in);
      toast.success(`Code sent to ${email.trim()}`);
    } catch (err) {
      toast.error(errorText(err, "Couldn't send the code"));
    } finally {
      working(false);
    }
  }

  async function verify(value = code) {
    if (value.length !== 6 || busy) return;
    working(true);
    try {
      const { access_token } = await api.verifyCode(email.trim(), value, mode);
      await finish(access_token, mode === "signup" ? "Account created — let's get started" : "Welcome back");
    } catch (err) {
      toast.error(errorText(err, "That code didn't work"));
      setCode("");
    } finally {
      working(false);
    }
  }

  if (step === "code") {
    return (
      <form
        onSubmit={(e) => {
          e.preventDefault();
          verify();
        }}
        className="space-y-4"
      >
        <div className="space-y-2">
          <Label htmlFor="code">6-digit code</Label>
          <CodeInput value={code} onChange={setCode} onComplete={verify} disabled={busy} />
          <p className="text-xs leading-relaxed text-muted-foreground">
            Sent to <span className="font-medium text-foreground">{email.trim()}</span>. It expires in 10 minutes; check spam
            if it isn&apos;t there.
          </p>
        </div>
        <Button type="submit" className="w-full" disabled={busy || code.length !== 6} size="lg">
          {busy ? (
            <Working>Verifying…</Working>
          ) : (
            <>
              {mode === "signup" ? "Create account" : "Sign in"} <ArrowRight className="size-4" />
            </>
          )}
        </Button>
        <div className="flex items-center justify-between text-xs">
          <button
            type="button"
            onClick={() => setStep("email")}
            className="flex items-center gap-1 text-muted-foreground transition-colors hover:text-foreground"
          >
            <ArrowLeft className="size-3" /> Change email
          </button>
          <button
            type="button"
            onClick={() => send()}
            disabled={resendIn > 0 || busy}
            className="text-muted-foreground hover:text-foreground disabled:opacity-50"
          >
            {resendIn > 0 ? `Resend in ${resendIn}s` : "Resend code"}
          </button>
        </div>
      </form>
    );
  }

  return (
    <form onSubmit={send} className="space-y-4">
      {mode === "signup" && (
        <div className="space-y-1.5">
          <Label htmlFor="name">Name</Label>
          <Input id="name" placeholder="Ada Lovelace" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" />
        </div>
      )}
      <div className="space-y-1.5">
        <Label htmlFor="email">Email</Label>
        <Input
          id="email"
          type="email"
          placeholder="ada@team.dev"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          autoComplete="email"
        />
      </div>
      <Button type="submit" className="w-full" disabled={busy || !email.trim()} size="lg">
        {busy ? (
          <Working>Sending code…</Working>
        ) : (
          <>
            <Mail className="size-4" /> Email me a code
          </>
        )}
      </Button>
    </form>
  );
}

/* ---------- Password (kept for existing accounts) ---------- */

function PasswordForm({ mode, onBusy }: { mode: Mode; onBusy: (b: boolean) => void }) {
  const finish = useFinish();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    onBusy(true);
    try {
      const { access_token } =
        mode === "signup"
          ? await api.register(name.trim(), email.trim(), password)
          : await api.login(email.trim(), password);
      await finish(access_token, mode === "signup" ? "Account created — let's get started" : "Welcome back");
    } catch (err) {
      toast.error(errorText(err, mode === "signup" ? "Sign up failed" : "Sign in failed"));
    } finally {
      setBusy(false);
      onBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      {mode === "signup" && (
        <div className="space-y-1.5">
          <Label htmlFor="pw-name">Name</Label>
          <Input id="pw-name" placeholder="Ada Lovelace" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" />
        </div>
      )}
      <div className="space-y-1.5">
        <Label htmlFor="pw-email">Email</Label>
        <Input
          id="pw-email"
          type="email"
          placeholder="ada@team.dev"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          autoComplete="email"
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="pw-password">Password</Label>
        <PasswordInput
          id="pw-password"
          value={password}
          onChange={(e) => setPassword((e.target as HTMLInputElement).value)}
          placeholder={mode === "signup" ? "8+ characters" : "••••••••"}
          minLength={mode === "signup" ? 8 : undefined}
          required
        />
      </div>
      <Button type="submit" className="w-full" disabled={busy} size="lg">
        {busy ? (
          <Working>{mode === "signup" ? "Creating account…" : "Signing in…"}</Working>
        ) : (
          <>
            {mode === "signup" ? "Create account" : "Sign in"} <ArrowRight className="size-4" />
          </>
        )}
      </Button>
    </form>
  );
}

/* ---------- Pages ---------- */

function AuthPage({ mode }: { mode: Mode }) {
  const { cfg, error: cfgError, retry } = useAuthConfig();
  const [busy, setBusy] = useState(false);
  const [method, setMethod] = useState<"code" | "password">("code");
  const signup = mode === "signup";
  const pose: Pose = busy ? "thinking" : signup ? "excited" : "happy";

  return (
    <main className="grid min-h-[calc(100dvh-3.5rem)] lg:grid-cols-[1fr_minmax(0,34rem)]">
      <section className="flex items-center justify-center px-4 py-10 sm:px-8">
        <div className="w-full max-w-sm animate-enter-up">
          <div className="mb-6 flex items-center gap-3 lg:hidden">
            <Sherpa pose={pose} size={56} decorative />
            <p className="eyebrow">Codebase mentor</p>
          </div>
          <h1 className="text-2xl font-semibold">{signup ? "Create your account" : "Welcome back"}</h1>
          <p className="mt-1.5 text-sm text-muted-foreground">
            {signup ? "No password needed. We email you a sign-in code." : "Sign in to pick up where you left off."}
          </p>

          <div className="mt-7 space-y-5">
            {cfgError && (
              <div role="alert" className="rounded-lg border border-destructive/40 bg-destructive/5 px-3 py-2.5 text-xs">
                <p className="font-medium text-destructive">Sign-in options couldn&apos;t load</p>
                <p className="mt-1 break-words text-muted-foreground">
                  {cfgError} Google and GitHub sign-in appear once the API answers.
                </p>
                <button type="button" onClick={retry} className="mt-1.5 font-medium text-foreground underline underline-offset-2">
                  Try again
                </button>
              </div>
            )}
            {(cfg?.google_client_id || cfg?.github) && (
              <>
                <div className="space-y-2.5">
                  {cfg.google_client_id && <GoogleButton clientId={cfg.google_client_id} mode={mode} onBusy={setBusy} />}
                  {cfg.github && <GitHubButton mode={mode} onBusy={setBusy} />}
                </div>
                <div className="eyebrow flex items-center gap-3">
                  <span className="h-px flex-1 bg-border" />
                  or
                  <span className="h-px flex-1 bg-border" />
                </div>
              </>
            )}

            {method === "code" ? <EmailCodeForm mode={mode} onBusy={setBusy} /> : <PasswordForm mode={mode} onBusy={setBusy} />}

            <button
              type="button"
              onClick={() => setMethod((m) => (m === "code" ? "password" : "code"))}
              className="w-full text-center text-[13px] text-muted-foreground transition-colors hover:text-foreground"
            >
              {method === "code" ? `${signup ? "Sign up" : "Sign in"} with a password instead` : "Use an email code instead"}
            </button>
          </div>

          <p className="mt-8 border-t border-border pt-5 text-sm text-muted-foreground">
            {signup ? "Already have an account? " : "New to Sherpa? "}
            <Link href={signup ? "/login" : "/signup"} className="font-medium text-primary underline-offset-4 hover:underline">
              {signup ? "Sign in" : "Create an account"}
            </Link>
          </p>
        </div>
      </section>

      {/* the guide, on the navy card from the logo sheet */}
      <aside className="relative hidden flex-col justify-between overflow-hidden border-l border-border bg-navy p-10 text-cream lg:flex">
        <p className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-sky-brand">Sherpa AI · Codebase mentor</p>
        <div className="flex flex-col items-start gap-6">
          <div className="max-w-xs rounded-lg border border-white/10 bg-white/[0.06] px-4 py-3 text-[15px] leading-relaxed">
            {busy
              ? "One moment, checking that for you…"
              : signup
                ? "Hi! I'm Sherpa. Point me at a repository and I'll show you around, with the file and line for everything I say."
                : "Good to see you again. Your repositories are right where you left them."}
          </div>
          <Sherpa pose={pose} size={192} />
        </div>
        <ul className="grid gap-2 text-sm text-cream/70">
          {["Answers cite exact files and lines", "Architecture maps and guided tours", "GitHub, ZIP, folder or CLI"].map((t) => (
            <li key={t} className="flex items-center gap-2.5">
              <span aria-hidden className="size-1.5 bg-tan" />
              {t}
            </li>
          ))}
        </ul>
      </aside>
    </main>
  );
}

export function LoginForm() {
  return <AuthPage mode="login" />;
}

export function SignupForm() {
  return <AuthPage mode="signup" />;
}
