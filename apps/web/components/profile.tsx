"use client";

/* Profile: who you are in Sherpa, how you sign in (connect or disconnect Google and GitHub),
 * and what you've done so far. */

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { toast } from "sonner";
import { Check, FolderGit2, Github, GraduationCap, KeyRound, Loader2, LogOut, Mail, Pencil, Trophy, X, FileCode2 } from "lucide-react";
import { api, ApiError, tokenStore, type Profile as ProfileData } from "../lib/api";
import { useAuth } from "../lib/auth";
import { isNativeApp } from "../lib/desktop";
import { startGitHub } from "../lib/github-auth";
import { loadGsi } from "./auth-forms";
import { Badge, Button, ConfirmDialog, Input } from "./ui/primitives";

const errorText = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);

function GoogleMark() {
  return (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden>
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1z" />
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23z" />
      <path fill="#FBBC05" d="M5.84 14.09A6.6 6.6 0 0 1 5.5 12c0-.73.13-1.43.34-2.09V7.07H2.18A11 11 0 0 0 1 12c0 1.78.43 3.45 1.18 4.93l3.66-2.84z" />
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1A11 11 0 0 0 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
    </svg>
  );
}

function Avatar({ p }: { p: ProfileData }) {
  const [broken, setBroken] = useState(false);
  const letter = (p.name || p.email).trim().slice(0, 1).toUpperCase() || "?";
  if (p.sign_in.github && !broken) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={`https://github.com/${p.sign_in.github}.png?size=144`} alt="" onError={() => setBroken(true)} className="size-16 shrink-0 rounded-full border border-border object-cover" />;
  }
  return <span className="flex size-16 shrink-0 items-center justify-center rounded-full border border-border bg-cream text-2xl font-semibold text-navy">{letter}</span>;
}

function Stat({ icon: Icon, label, value }: { icon: typeof Trophy; label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <p className="eyebrow flex items-center gap-1.5"><Icon className="size-3.5" />{label}</p>
      <p className="mt-2 text-2xl font-semibold tabular-nums">{value}</p>
    </div>
  );
}

function Meter({ label, used, limit }: { label: string; used: number; limit: number }) {
  const pct = limit ? Math.min(100, (100 * used) / limit) : 0;
  return (
    <div>
      <div className="flex justify-between text-xs"><span>{label}</span><span className="tabular-nums text-muted-foreground">{used} / {limit}</span></div>
      <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-secondary">
        <div className="h-full rounded-full bg-primary transition-[width] duration-500" style={{ width: `${Math.max(pct, used ? 2 : 0)}%` }} />
      </div>
    </div>
  );
}

/** Google's own button, wired to "connect to this account" instead of signing in. */
function ConnectGoogle({ clientId, onLinked }: { clientId: string; onLinked: (p: ProfileData) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const { resolvedTheme } = useTheme();
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
            try {
              onLinked(await api.linkGoogle(credential));
              toast.success("Google connected");
            } catch (e) {
              toast.error(errorText(e, "Couldn't connect Google"));
            }
          },
        });
        window.google.accounts.id.renderButton(ref.current, {
          theme: resolvedTheme === "dark" ? "filled_black" : "outline", size: "medium", text: "continue_with", shape: "rectangular",
        });
      })
      .catch(() => setFailed(true));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId, resolvedTheme]);
  if (failed) return <span className="text-xs text-muted-foreground">Google couldn&apos;t load</span>;
  return <div ref={ref} className="min-h-[32px]" />;
}

function Method({ icon, name, detail, state, action, linked = false }: {
  icon: React.ReactNode; name: string; detail: React.ReactNode; state: "on" | "off"; action?: React.ReactNode; linked?: boolean;
}) {
  return (
    <li className="flex flex-wrap items-center gap-3 px-5 py-4">
      <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-secondary">{icon}</span>
      <div className="min-w-0 flex-1">
        <p className="flex items-center gap-2 text-sm font-medium">
          {name}
          {state === "on" ? <Badge variant="success">{linked ? "Connected" : "On"}</Badge> : <Badge variant="outline">{linked ? "Not connected" : "Off"}</Badge>}
        </p>
        <p className="truncate text-xs text-muted-foreground">{detail}</p>
      </div>
      {action}
    </li>
  );
}

export function Profile() {
  const { user, loading, signIn, signOut } = useAuth();
  const router = useRouter();
  const [p, setP] = useState<ProfileData | null>(null);
  const [cfg, setCfg] = useState<{ google_client_id: string | null; github?: boolean } | null>(null);
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [unlinking, setUnlinking] = useState<"google" | "github" | null>(null);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);
  useEffect(() => {
    if (!user) return;
    api.profile().then(setP).catch((e) => toast.error(errorText(e, "Couldn't load your profile")));
    api.authConfig().then((c) => setCfg(isNativeApp() ? { google_client_id: null, github: false } : c)).catch(() => setCfg({ google_client_id: null }));
  }, [user]);

  if (!p) {
    return (
      <main className="container flex h-[calc(100vh_-_var(--header-h))] items-center justify-center">
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
      </main>
    );
  }

  async function saveName(e?: React.FormEvent) {
    e?.preventDefault();
    setSaving(true);
    try {
      setP(await api.updateProfile(name));
      setEditing(false);
      const t = tokenStore.get();
      if (t) await signIn(t); // refresh the name in the header menu
      toast.success("Name updated");
    } catch (err) {
      toast.error(errorText(err, "Couldn't save your name"));
    } finally {
      setSaving(false);
    }
  }

  async function unlink(provider: "google" | "github") {
    try {
      setP(await api.unlink(provider));
      toast.success(`${provider === "google" ? "Google" : "GitHub"} disconnected`);
    } catch (e) {
      toast.error(errorText(e, "Couldn't disconnect"));
    }
  }

  const s = p.sign_in;
  const ways = [s.password, s.email_code, s.google, !!s.github].filter(Boolean).length;
  const since = p.created_at ? new Date(p.created_at).toLocaleDateString(undefined, { month: "long", year: "numeric" }) : "";

  return (
    <main className="container max-w-3xl space-y-6 py-10">
      {/* who you are */}
      <section className="flex flex-wrap items-center gap-5 rounded-xl border border-border bg-card p-6 shadow-card">
        <Avatar p={p} />
        <div className="min-w-0 flex-1">
          {editing ? (
            <form onSubmit={saveName} className="flex max-w-sm items-center gap-2">
              <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={120} autoFocus aria-label="Your name"
                onKeyDown={(e) => e.key === "Escape" && setEditing(false)} />
              <Button type="submit" size="icon" disabled={saving || !name.trim()} aria-label="Save name">
                {saving ? <Loader2 className="animate-spin" /> : <Check />}
              </Button>
              <Button variant="ghost" size="icon" onClick={() => setEditing(false)} aria-label="Cancel"><X /></Button>
            </form>
          ) : (
            <h1 className="flex items-center gap-2 text-2xl font-semibold">
              <span className="truncate">{p.name || "Add your name"}</span>
              <Button variant="ghost" size="icon-sm" aria-label="Edit name" onClick={() => { setName(p.name); setEditing(true); }}>
                <Pencil />
              </Button>
            </h1>
          )}
          <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <span className="truncate">{p.noreply_email ? "No email shared by GitHub" : p.email}</span>
            {!p.noreply_email && p.email_verified && <Badge variant="success">Verified</Badge>}
          </p>
          {since && <p className="mt-0.5 text-xs text-muted-foreground">Member since {since}</p>}
        </div>
        <Button variant="outline" className="w-full sm:w-auto" onClick={() => { signOut(); router.push("/"); }}>
          <LogOut /> Sign out
        </Button>
      </section>

      {/* what you've done */}
      <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat icon={FolderGit2} label="Repositories" value={p.stats.repos} />
        <Stat icon={FileCode2} label="Files indexed" value={p.stats.files.toLocaleString()} />
        <Stat icon={GraduationCap} label="Skill checks" value={p.stats.quizzes} />
        <Stat icon={Trophy} label="Best score" value={p.stats.best_score == null ? "–" : `${p.stats.best_score}%`} />
      </section>

      <section className="rounded-xl border border-border bg-card p-5">
        <p className="eyebrow">Today&apos;s usage</p>
        <div className="mt-3 grid gap-4 sm:grid-cols-2">
          <Meter label="AI requests" used={p.today.llm} limit={p.today.llm_limit} />
          <Meter label="Repositories indexed" used={p.today.ingest} limit={p.today.ingest_limit} />
        </div>
        <p className="mt-3 text-[11px] text-muted-foreground">Limits reset at midnight UTC. Add your own model key under Keys &amp; endpoints to use it instead.</p>
      </section>

      {/* how you sign in */}
      <section className="overflow-hidden rounded-xl border border-border bg-card">
        <div className="border-b border-border px-5 py-4">
          <h2 className="text-sm font-semibold">Sign-in methods</h2>
          <p className="text-xs text-muted-foreground">Connect more than one so you never get locked out. Any of them opens this same account.</p>
        </div>
        <ul className="divide-y divide-border">
          <Method
            icon={<Mail className="size-4" />}
            name="Email code"
            state={s.email_code ? "on" : "off"}
            detail={s.email_code ? `A one-time code sent to ${p.email}` : "Unavailable: GitHub didn't share an email address"}
          />
          <Method icon={<KeyRound className="size-4" />} name="Password" state={s.password ? "on" : "off"}
            detail={s.password ? "Sign in with your email and password" : "Not set: you sign in another way"} />
          <Method
            icon={<GoogleMark />}
            name="Google"
            linked
            state={s.google ? "on" : "off"}
            detail={s.google ? "Continue with Google opens this account" : "Use your Google account to sign in here"}
            action={s.google ? (
              <Button variant="ghost" size="sm" onClick={() => setUnlinking("google")}>Disconnect</Button>
            ) : cfg?.google_client_id ? (
              <ConnectGoogle clientId={cfg.google_client_id} onLinked={setP} />
            ) : null}
          />
          <Method
            icon={<Github className="size-4" />}
            name="GitHub"
            linked
            state={s.github ? "on" : "off"}
            detail={s.github ? <>Signed in as <span className="font-mono">@{s.github}</span>, and your public repos are one click away</> : "Sign in with GitHub and pick from your own repositories"}
            action={s.github ? (
              <Button variant="ghost" size="sm" onClick={() => setUnlinking("github")}>Disconnect</Button>
            ) : cfg?.github ? (
              <Button variant="outline" size="sm" onClick={() => startGitHub({ link: true, next: "/profile" }).catch((e) => toast.error(errorText(e, "GitHub is unavailable right now")))}>
                <Github /> Connect
              </Button>
            ) : null}
          />
        </ul>
      </section>

      <ConfirmDialog
        open={unlinking !== null}
        onOpenChange={(o) => !o && setUnlinking(null)}
        title={`Disconnect ${unlinking === "google" ? "Google" : "GitHub"}?`}
        description={ways <= 1
          ? "This is your only way to sign in, so it can't be removed yet. Connect another account first."
          : `You won't be able to sign in with ${unlinking === "google" ? "Google" : "GitHub"} until you connect it again. Your repositories stay as they are.`}
        confirmLabel="Disconnect"
        onConfirm={() => unlinking && unlink(unlinking)}
      />
    </main>
  );
}
