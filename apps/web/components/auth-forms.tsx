"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { ArrowLeft, ArrowRight, Eye, EyeOff, Mail } from "lucide-react";
import { api, ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Button, Input, Label } from "./ui/primitives";
import { SherpaOrb } from "./sherpa-orb";

const ease = [0.22, 1, 0.36, 1] as const;
type Mode = "login" | "signup";
type AuthConfig = { google_client_id: string | null; email_otp: boolean; password: boolean };

function rise(i: number) {
  return {
    initial: { opacity: 0, y: 14 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.5, delay: i * 0.07, ease },
  };
}

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
  useEffect(() => {
    api.authConfig().then(setCfg).catch(() => setCfg({ google_client_id: null, email_otp: true, password: true }));
  }, []);
  return cfg;
}

function Dots() {
  return (
    <span className="flex gap-1">
      {[0, 1, 2].map((i) => (
        <motion.span
          key={i}
          className="block h-1 w-1 rounded-full bg-primary-foreground"
          animate={{ y: [0, -3, 0] }}
          transition={{ duration: 0.8, delay: i * 0.15, repeat: Infinity }}
        />
      ))}
    </span>
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
function loadGsi(): Promise<void> {
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
          theme: "filled_black",
          size: "large",
          shape: "pill",
          text: mode === "signup" ? "signup_with" : "continue_with",
          width: Math.min(ref.current.offsetWidth || 320, 400),
        });
      })
      .catch(() => setFailed(true));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId, mode]);

  if (failed) {
    return <p className="text-center text-xs text-muted-foreground">Google sign-in couldn&apos;t load. Use an email code instead.</p>;
  }
  return <div ref={ref} className="flex min-h-[44px] w-full justify-center" />;
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
        <div className="space-y-1.5">
          <Label htmlFor="code">6-digit code</Label>
          <Input
            id="code"
            value={code}
            onChange={(e) => {
              const v = e.target.value.replace(/\D/g, "").slice(0, 6);
              setCode(v);
              if (v.length === 6) verify(v);
            }}
            inputMode="numeric"
            autoComplete="one-time-code"
            placeholder="••••••"
            className="h-12 text-center font-mono text-xl tracking-[0.5em]"
            autoFocus
          />
          <p className="text-xs text-muted-foreground">
            Sent to <span className="text-foreground">{email.trim()}</span>. It expires in 10 minutes. Check spam if it
            isn&apos;t there.
          </p>
        </div>
        <Button className="w-full" disabled={busy || code.length !== 6} size="lg">
          {busy ? (
            <span className="flex items-center gap-2">
              <Dots /> Verifying…
            </span>
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
            className="flex items-center gap-1 text-muted-foreground hover:text-foreground"
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
      <Button className="w-full" disabled={busy || !email.trim()} size="lg">
        {busy ? (
          <span className="flex items-center gap-2">
            <Dots /> Sending code…
          </span>
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
      <Button className="w-full" disabled={busy} size="lg">
        {busy ? (
          <span className="flex items-center gap-2">
            <Dots /> {mode === "signup" ? "Creating account…" : "Signing in…"}
          </span>
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
  const cfg = useAuthConfig();
  const [busy, setBusy] = useState(false);
  const [method, setMethod] = useState<"code" | "password">("code");
  const signup = mode === "signup";

  return (
    <main className="flex min-h-[calc(100vh-3.5rem)] items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm">
        <motion.div {...rise(0)} className="mb-8 flex justify-center">
          <SherpaOrb size="lg" state={busy ? "thinking" : "idle"} />
        </motion.div>

        <motion.div {...rise(1)} className="mb-6 text-center">
          <h1 className="text-2xl font-semibold tracking-tight">{signup ? "Create your account" : "Welcome back"}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {signup ? "No password needed. Ready in 20 seconds." : "Sign in to your Sherpa workspace"}
          </p>
        </motion.div>

        <motion.div {...rise(2)} className="space-y-5 rounded-2xl border border-border bg-card p-6">
          {cfg?.google_client_id && (
            <>
              <GoogleButton clientId={cfg.google_client_id} mode={mode} onBusy={setBusy} />
              <div className="flex items-center gap-3 text-[11px] uppercase tracking-wider text-muted-foreground">
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
            className="w-full text-center text-xs text-muted-foreground hover:text-foreground"
          >
            {method === "code" ? `${signup ? "Sign up" : "Sign in"} with a password instead` : "Use an email code instead"}
          </button>

          <p className="border-t border-border pt-4 text-center text-sm text-muted-foreground">
            {signup ? "Already have an account? " : "No account? "}
            <Link
              href={signup ? "/login" : "/signup"}
              className="font-medium text-foreground underline-offset-4 hover:underline"
            >
              {signup ? "Sign in" : "Create one free"}
            </Link>
          </p>
        </motion.div>
      </div>
    </main>
  );
}

export function LoginForm() {
  return <AuthPage mode="login" />;
}

export function SignupForm() {
  return <AuthPage mode="signup" />;
}
