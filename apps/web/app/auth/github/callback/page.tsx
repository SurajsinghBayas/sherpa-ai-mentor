"use client";

/* GitHub sends the browser here after the user approves Sherpa (see lib/github-auth.ts). */

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { api, ApiError } from "../../../../lib/api";
import { useAuth } from "../../../../lib/auth";
import { callbackUrl, takeGitHubState } from "../../../../lib/github-auth";
import { Sherpa } from "../../../../components/sherpa";

export default function GitHubCallbackPage() {
  const { signIn } = useAuth();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const ran = useRef(false); // strict mode runs effects twice; a code works only once

  useEffect(() => {
    if (ran.current) return;
    ran.current = true;
    const q = new URLSearchParams(window.location.search);
    const { state, next } = takeGitHubState();
    if (q.get("error")) return setError(q.get("error") === "access_denied" ? "You cancelled the GitHub sign-in." : "GitHub didn't sign you in.");
    if (!q.get("code") || !state || q.get("state") !== state) return setError("This sign-in link didn't start in this tab. Please try again.");
    api
      .github(q.get("code")!, state, callbackUrl())
      .then(async ({ access_token }) => {
        await signIn(access_token);
        toast.success("Signed in with GitHub");
        router.replace(next);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "GitHub sign-in failed"));
  }, [router, signIn]);

  return (
    <main className="grid min-h-[calc(100dvh_-_var(--header-h))] place-items-center px-4">
      <div className="flex max-w-sm flex-col items-center gap-4 text-center">
        <Sherpa pose={error ? "guide" : "thinking"} size={96} decorative />
        {error ? (
          <>
            <p className="text-sm">{error}</p>
            <Link href="/login" className="text-sm font-medium text-primary underline-offset-4 hover:underline">
              Back to sign in
            </Link>
          </>
        ) : (
          <p className="text-sm text-muted-foreground" role="status">Finishing GitHub sign-in…</p>
        )}
      </div>
    </main>
  );
}
