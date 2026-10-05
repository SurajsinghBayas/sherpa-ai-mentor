"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { ArrowRight, Eye, EyeOff } from "lucide-react";
import { api, ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Button, Input, Label } from "./ui/primitives";
import { SherpaOrb } from "./sherpa-orb";

const ease = [0.22, 1, 0.36, 1] as const;

function rise(i: number) {
  return {
    initial: { opacity: 0, y: 14 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.5, delay: i * 0.07, ease },
  };
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
        className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
      >
        {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
      </button>
    </div>
  );
}

export function LoginForm() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const { signIn } = useAuth();
  const router = useRouter();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const { access_token } = await api.login(email.trim(), password);
      await signIn(access_token);
      toast.success("Welcome back");
      router.push("/dashboard");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Sign in failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-[calc(100vh-3.5rem)] items-center justify-center px-4">
      <div className="w-full max-w-sm">
        {/* Orb */}
        <motion.div {...rise(0)} className="mb-8 flex justify-center">
          <SherpaOrb size="lg" state={busy ? "thinking" : "idle"} />
        </motion.div>

        <motion.div {...rise(1)} className="mb-6 text-center">
          <h1 className="text-2xl font-semibold tracking-tight">Welcome back</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Sign in to your Sherpa workspace
          </p>
        </motion.div>

        <motion.form
          {...rise(2)}
          onSubmit={submit}
          className="space-y-4 rounded-2xl border border-border bg-card p-6"
        >
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

          <div className="space-y-1.5">
            <Label htmlFor="password">Password</Label>
            <PasswordInput
              id="password"
              value={password}
              onChange={(e) => setPassword((e.target as HTMLInputElement).value)}
              placeholder="••••••••"
              required
            />
          </div>

          <Button className="w-full" disabled={busy} size="lg">
            {busy ? (
              <span className="flex items-center gap-2">
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
                Signing in…
              </span>
            ) : (
              <>
                Sign in <ArrowRight className="size-4" />
              </>
            )}
          </Button>

          <p className="text-center text-sm text-muted-foreground">
            No account?{" "}
            <Link href="/signup" className="font-medium text-foreground hover:underline underline-offset-4">
              Create one free
            </Link>
          </p>
        </motion.form>
      </div>
    </main>
  );
}

export function SignupForm() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const { signIn } = useAuth();
  const router = useRouter();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const { access_token } = await api.register(name.trim(), email.trim(), password);
      await signIn(access_token);
      toast.success("Account created — let's get started");
      router.push("/dashboard");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Sign up failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-[calc(100vh-3.5rem)] items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <motion.div {...rise(0)} className="mb-8 flex justify-center">
          <SherpaOrb size="lg" state={busy ? "thinking" : "idle"} />
        </motion.div>

        <motion.div {...rise(1)} className="mb-6 text-center">
          <h1 className="text-2xl font-semibold tracking-tight">Create your account</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Ready in 20 seconds. Free to start.
          </p>
        </motion.div>

        <motion.form
          {...rise(2)}
          onSubmit={submit}
          className="space-y-4 rounded-2xl border border-border bg-card p-6"
        >
          <div className="space-y-1.5">
            <Label htmlFor="name">Name</Label>
            <Input
              id="name"
              placeholder="Ada Lovelace"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoComplete="name"
            />
          </div>

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

          <div className="space-y-1.5">
            <Label htmlFor="password">Password</Label>
            <PasswordInput
              id="password"
              value={password}
              onChange={(e) => setPassword((e.target as HTMLInputElement).value)}
              placeholder="8+ characters"
              minLength={8}
              required
            />
          </div>

          <Button className="w-full" disabled={busy} size="lg">
            {busy ? (
              <span className="flex items-center gap-2">
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
                Creating account…
              </span>
            ) : (
              <>
                Create account <ArrowRight className="size-4" />
              </>
            )}
          </Button>

          <p className="text-center text-sm text-muted-foreground">
            Already have an account?{" "}
            <Link href="/login" className="font-medium text-foreground hover:underline underline-offset-4">
              Sign in
            </Link>
          </p>
        </motion.form>
      </div>
    </main>
  );
}
