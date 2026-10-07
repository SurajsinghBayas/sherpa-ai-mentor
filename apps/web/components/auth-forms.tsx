"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { api, ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label } from "./ui/primitives";

function Shell({ title, sub, children }: { title: string; sub: string; children: React.ReactNode }) {
  return (
    <main className="container flex min-h-[calc(100vh-3.5rem)] items-center justify-center py-12">
      <Card className="w-full max-w-sm animate-scale-in">
        <CardHeader><CardTitle>{title}</CardTitle><CardDescription>{sub}</CardDescription></CardHeader>
        <CardContent>{children}</CardContent>
      </Card>
    </main>
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
    <Shell title="Sign in" sub="Your repos and keys are waiting.">
      <form onSubmit={submit} className="space-y-4">
        <div className="space-y-2"><Label htmlFor="email">Email</Label>
          <Input id="email" type="email" placeholder="ada@team.dev" value={email} onChange={(e) => setEmail(e.target.value)} required /></div>
        <div className="space-y-2"><Label htmlFor="password">Password</Label>
          <Input id="password" type="password" placeholder="••••••••" value={password} onChange={(e) => setPassword(e.target.value)} required /></div>
        <Button className="w-full" disabled={busy}>{busy && <Loader2 className="animate-spin" />} Sign in</Button>
        <p className="text-center text-sm text-muted-foreground">No account? <Link href="/signup" className="text-foreground underline underline-offset-4">Sign up</Link></p>
      </form>
    </Shell>
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
      toast.success("Account created — add a repo to begin");
      router.push("/dashboard");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Sign up failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Shell title="Create account" sub="Free for the hackathon. Yours in 20 seconds.">
      <form onSubmit={submit} className="space-y-4">
        <div className="space-y-2"><Label htmlFor="name">Name</Label>
          <Input id="name" placeholder="Ada Lovelace" value={name} onChange={(e) => setName(e.target.value)} /></div>
        <div className="space-y-2"><Label htmlFor="email">Email</Label>
          <Input id="email" type="email" placeholder="ada@team.dev" value={email} onChange={(e) => setEmail(e.target.value)} required /></div>
        <div className="space-y-2"><Label htmlFor="password">Password</Label>
          <Input id="password" type="password" placeholder="8+ characters" minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} required /></div>
        <Button className="w-full" disabled={busy}>{busy && <Loader2 className="animate-spin" />} Create account</Button>
        <p className="text-center text-sm text-muted-foreground">Have an account? <Link href="/login" className="text-foreground underline underline-offset-4">Sign in</Link></p>
      </form>
    </Shell>
  );
}
