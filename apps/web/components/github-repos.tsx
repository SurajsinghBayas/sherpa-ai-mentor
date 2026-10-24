"use client";

/* The signed-in user's public GitHub repos, one click to index. Users who signed in another way
 * can connect GitHub here; the list then appears. */

import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Github, Loader2, RotateCcw, Search, Star } from "lucide-react";
import { api, ApiError, type GitHubRepo } from "../lib/api";
import { useAuth } from "../lib/auth";
import { isNativeApp } from "../lib/desktop";
import { startGitHub } from "../lib/github-auth";
import { Badge, Button, Input } from "./ui/primitives";

function ago(iso: string) {
  const days = Math.floor((Date.now() - Date.parse(iso)) / 86400000);
  if (!iso || Number.isNaN(days)) return "";
  if (days < 1) return "today";
  if (days < 30) return `${days} d ago`;
  if (days < 365) return `${Math.floor(days / 30)} mo ago`;
  return `${Math.floor(days / 365)} y ago`;
}

export function GitHubRepos({
  indexing,
  onIndex,
  onOpen,
}: {
  indexing: string | null; // the URL being indexed right now
  onIndex: (url: string) => void;
  onOpen: (repoId: string) => void;
}) {
  const { user } = useAuth();
  const login = user?.github_login;
  const [enabled, setEnabled] = useState(false);
  const [repos, setRepos] = useState<GitHubRepo[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");

  useEffect(() => {
    if (isNativeApp()) return; // GitHub only sends people back to web origins
    api.authConfig().then((c) => setEnabled(!!c.github)).catch(() => {});
  }, []);

  async function load(refresh = false) {
    setLoading(true);
    setError(null);
    try {
      setRepos((await api.githubRepos(refresh)).repos);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't load your repositories");
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    if (login) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [login, indexing === null]); // reload after an index finishes so it shows as indexed

  const shown = useMemo(() => {
    const t = q.trim().toLowerCase();
    return (repos ?? []).filter((r) => !t || r.name.toLowerCase().includes(t) || r.description.toLowerCase().includes(t));
  }, [repos, q]);

  if (!enabled && !login) return null;

  if (!login) {
    return (
      <div className="mt-3 flex flex-wrap items-center gap-3 rounded-lg border border-dashed border-input px-3 py-2.5 text-xs text-muted-foreground">
        <Github className="size-4 shrink-0" />
        <span className="mr-auto">Connect GitHub to pick from your own repositories.</span>
        <Button
          size="sm"
          variant="outline"
          onClick={() => startGitHub({ link: true }).catch((e) => toast.error(e instanceof ApiError ? e.message : "GitHub is unavailable right now"))}
        >
          Connect GitHub
        </Button>
      </div>
    );
  }

  return (
    <div className="mt-4 rounded-lg border border-border bg-card">
      <div className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-2">
        <Github className="size-4 shrink-0 text-muted-foreground" />
        <p className="mr-auto text-xs">
          <span className="font-medium">Your public repositories</span>
          <span className="text-muted-foreground"> · @{login}{repos ? ` · ${repos.length}` : ""}</span>
        </p>
        {(repos?.length ?? 0) > 6 && (
          <div className="relative order-last w-full sm:order-none sm:w-48">
            <Search className="pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter" aria-label="Filter repositories" className="h-7 pl-7 text-xs" />
          </div>
        )}
        <Button variant="ghost" size="icon-sm" onClick={() => load(true)} disabled={loading} aria-label="Refresh the list">
          <RotateCcw className={loading ? "animate-spin" : ""} />
        </Button>
      </div>
      {error ? (
        <p className="px-3 py-4 text-xs text-destructive">{error}</p>
      ) : !repos ? (
        <p className="flex items-center gap-2 px-3 py-4 text-xs text-muted-foreground"><Loader2 className="size-3.5 animate-spin" /> Loading your repositories</p>
      ) : !shown.length ? (
        <p className="px-3 py-4 text-xs text-muted-foreground">{repos.length ? "No repository matches that filter." : "No public repositories on this GitHub account yet."}</p>
      ) : (
        <ul className="scroll-thin max-h-[max(18rem,calc(100dvh-26rem))] divide-y divide-border overflow-y-auto">
          {shown.map((r) => {
            const busy = indexing === r.url;
            return (
              <li key={r.full_name} className="flex items-center gap-3 px-3 py-2">
                <div className="min-w-0 flex-1">
                  <p className="flex items-center gap-1.5 text-[13px]">
                    <span className="truncate font-mono">{r.name}</span>
                    {r.fork && <Badge className="shrink-0">fork</Badge>}
                    {r.archived && <Badge className="shrink-0">archived</Badge>}
                  </p>
                  <p className="truncate text-[11px] text-muted-foreground">
                    {[r.language, ago(r.pushed_at)].filter(Boolean).join(" · ")}
                    {r.stars > 0 && (
                      <span className="ml-1.5 inline-flex items-center gap-0.5"><Star className="size-3" />{r.stars}</span>
                    )}
                    {r.description && <span> · {r.description}</span>}
                  </p>
                </div>
                {r.repo_id ? (
                  <Button size="sm" variant="ghost" onClick={() => onOpen(r.repo_id!)}>Open</Button>
                ) : (
                  <Button size="sm" variant="outline" onClick={() => onIndex(r.url)} disabled={!!indexing}>
                    {busy ? <><Loader2 className="animate-spin" /> Indexing</> : "Index"}
                  </Button>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
