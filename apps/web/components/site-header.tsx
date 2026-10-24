"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useTheme } from "next-themes";
import { KeyRound, LogOut, Moon, Sun, Terminal, UserRound } from "lucide-react";
import { useAuth } from "../lib/auth";
import { cn } from "../lib/utils";
import { Wordmark } from "./sherpa";
import { Button, buttonVariants, Menu, Tooltip } from "./ui/primitives";

const NAV_LINKS = [
  { href: "/dashboard", label: "Workspace" },
  { href: "/cli", label: "CLI" },
  { href: "/study", label: "User study" },
  { href: "/settings", label: "Keys" },
];

export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const dark = mounted && resolvedTheme === "dark";
  const label = dark ? "Switch to light theme" : "Switch to dark theme";
  return (
    <Tooltip content={label} side="bottom">
      <Button variant="ghost" size="icon" aria-label={label} onClick={() => setTheme(dark ? "light" : "dark")}>
        {dark ? <Sun /> : <Moon />}
      </Button>
    </Tooltip>
  );
}

function initials(s: string) {
  return s.trim().slice(0, 1).toUpperCase() || "?";
}

export function SiteHeader() {
  const { user, signOut } = useAuth();
  const path = usePathname();
  const router = useRouter();

  return (
    <header className="sticky top-0 z-header w-full border-b border-border bg-background">
      <div className={cn("flex h-14 items-center gap-3 px-4", path === "/dashboard" ? "" : "container")}>
        <Link href="/" aria-label="Sherpa AI home" className="rounded-md transition-opacity hover:opacity-80">
          <Wordmark />
        </Link>

        {user && (
          <nav aria-label="Main" className="no-scrollbar ml-2 flex min-w-0 items-center gap-0.5 overflow-x-auto sm:ml-4">
            {NAV_LINKS.map(({ href, label }) => (
              <Link
                key={href}
                href={href}
                aria-current={path === href ? "page" : undefined}
                className={cn(
                  "whitespace-nowrap rounded-md px-2.5 py-1.5 text-[13px] font-medium transition-colors duration-150",
                  path === href ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground"
                )}
              >
                {label}
              </Link>
            ))}
          </nav>
        )}

        <div className="ml-auto flex shrink-0 items-center gap-1">
          <ThemeToggle />
          {user ? (
            <Menu.Root>
              <Menu.Trigger
                aria-label="Account"
                className="ml-1 flex size-8 items-center justify-center rounded-full border border-border bg-cream text-[13px] font-semibold text-navy transition-transform duration-150 active:scale-[0.96]"
              >
                {initials(user.name || user.email)}
              </Menu.Trigger>
              <Menu.Popup align="end" className="w-60">
                <div className="px-2.5 pb-2 pt-1.5">
                  <p className="truncate text-sm font-medium">{user.name || "Signed in"}</p>
                  <p className="truncate text-xs text-muted-foreground">{user.email}</p>
                </div>
                <Menu.Separator />
                <Menu.Item onClick={() => router.push("/profile")}>
                  <UserRound /> Profile
                </Menu.Item>
                <Menu.Item onClick={() => router.push("/settings")}>
                  <KeyRound /> Keys & endpoints
                </Menu.Item>
                <Menu.Item onClick={() => router.push("/cli")}>
                  <Terminal /> Command-line tool
                </Menu.Item>
                <Menu.Separator />
                <Menu.Item
                  onClick={() => {
                    signOut();
                    router.push("/");
                  }}
                >
                  <LogOut /> Sign out
                </Menu.Item>
              </Menu.Popup>
            </Menu.Root>
          ) : (
            <>
              <Link href="/login" className={cn(buttonVariants({ variant: "ghost", size: "sm" }), "hidden sm:inline-flex")}>
                Sign in
              </Link>
              <Link href="/signup" className={buttonVariants({ variant: "ink", size: "sm" })}>
                Get started
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
