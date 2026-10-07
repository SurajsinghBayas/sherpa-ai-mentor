"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Mountain } from "lucide-react";
import { useAuth } from "../lib/auth";
import { Button } from "./ui/primitives";
import { cn } from "../lib/utils";

export function SiteHeader() {
  const { user, signOut } = useAuth();
  const path = usePathname();
  const router = useRouter();

  return (
    <header className="sticky top-0 z-40 w-full border-b bg-background/80 backdrop-blur-md">
      <div className="container flex h-14 items-center gap-6">
        <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
          <span className="flex size-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <Mountain className="size-4" />
          </span>
          Sherpa
        </Link>
        {user && (
          <nav className="flex items-center gap-1 text-sm">
            {[
              ["/dashboard", "Mentor"],
              ["/settings", "Keys & Endpoints"],
            ].map(([href, label]) => (
              <Link
                key={href}
                href={href}
                className={cn(
                  "rounded-md px-3 py-1.5 text-muted-foreground transition-colors hover:text-foreground",
                  path === href && "bg-secondary text-foreground"
                )}
              >
                {label}
              </Link>
            ))}
          </nav>
        )}
        <div className="ml-auto flex items-center gap-2">
          {user ? (
            <>
              <span className="hidden text-sm text-muted-foreground sm:block">{user.email}</span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  signOut();
                  router.push("/");
                }}
              >
                Sign out
              </Button>
            </>
          ) : (
            <>
              <Link href="/login">
                <Button variant="ghost" size="sm">Sign in</Button>
              </Link>
              <Link href="/signup">
                <Button size="sm">Get started</Button>
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
