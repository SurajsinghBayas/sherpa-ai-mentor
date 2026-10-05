"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "../lib/auth";
import { Button } from "./ui/primitives";
import { SherpaOrb } from "./sherpa-orb";
import { cn } from "../lib/utils";

const NAV_LINKS = [
  { href: "/dashboard", label: "Mentor" },
  { href: "/settings", label: "Keys" },
];

export function SiteHeader() {
  const { user, signOut } = useAuth();
  const path = usePathname();
  const router = useRouter();

  return (
    <header className="sticky top-0 z-50 w-full border-b border-border glass">
      <div className="container flex h-14 items-center gap-4">
        {/* logo */}
        <Link
          href="/"
          className="flex items-center gap-2 font-semibold tracking-tight transition-opacity hover:opacity-80"
        >
          <SherpaOrb size="xs" />
          <span>Sherpa</span>
        </Link>

        {/* nav (authenticated) */}
        {user && (
          <nav className="flex items-center gap-1 text-sm ml-2">
            {NAV_LINKS.map(({ href, label }) => (
              <Link
                key={href}
                href={href}
                className={cn(
                  "rounded-lg px-3 py-1.5 font-medium transition-colors duration-150",
                  path === href
                    ? "bg-secondary text-foreground"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                {label}
              </Link>
            ))}
          </nav>
        )}

        {/* right side */}
        <div className="ml-auto flex items-center gap-2">
          {user ? (
            <>
              <span className="hidden text-sm text-muted-foreground sm:block">
                {user.name || user.email}
              </span>
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
