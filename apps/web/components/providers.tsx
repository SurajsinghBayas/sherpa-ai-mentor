"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { ThemeProvider, useTheme } from "next-themes";
import { Toaster } from "sonner";
import { AuthProvider } from "../lib/auth";
import { isDesktop, isMobileApp, isNativeApp } from "../lib/desktop";
import { TooltipProvider } from "./ui/primitives";

function ThemedToaster() {
  const { resolvedTheme } = useTheme();
  return (
    <Toaster
      theme={resolvedTheme === "dark" ? "dark" : "light"}
      position="bottom-right"
      closeButton
      toastOptions={{
        classNames: {
          toast: "!rounded-xl !border-border !bg-card !text-card-foreground !shadow-pop !font-sans",
          description: "!text-muted-foreground",
        },
      }}
    />
  );
}

/** Desktop and mobile apps: the marketing page goes straight to the workspace. On desktop, links to
 *  other sites open in the default browser (the mobile shells already do that); on phones, the status
 *  bar icons follow the theme. */
function AppShell() {
  const path = usePathname();
  const router = useRouter();
  const { resolvedTheme } = useTheme();

  useEffect(() => {
    if (isNativeApp() && path === "/") router.replace("/dashboard");
  }, [path, router]);

  useEffect(() => {
    // the phone apps are fixed-scale like any native app: no pinch or double-tap zoom to pan around in
    if (!isMobileApp()) return;
    document
      .querySelector('meta[name="viewport"]')
      ?.setAttribute("content", "width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover");
  }, []);

  useEffect(() => {
    if (!isMobileApp()) return;
    import("@capacitor/core")
      .then(({ SystemBars, SystemBarsStyle }) =>
        SystemBars.setStyle({ style: resolvedTheme === "dark" ? SystemBarsStyle.Dark : SystemBarsStyle.Light }),
      )
      .catch(() => {});
  }, [resolvedTheme]);

  useEffect(() => {
    if (!isDesktop()) return;
    const onClick = (e: MouseEvent) => {
      const a = (e.target as HTMLElement | null)?.closest?.("a[href]") as HTMLAnchorElement | null;
      if (!a || !/^(https?:|mailto:)/.test(a.href) || new URL(a.href).origin === window.location.origin) return;
      e.preventDefault();
      import("@tauri-apps/plugin-opener").then(({ openUrl }) => openUrl(a.href)).catch(() => {});
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, []);

  return null;
}

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider attribute="class" defaultTheme="light" enableSystem disableTransitionOnChange>
      <TooltipProvider delay={400}>
        <AuthProvider>
          <AppShell />
          {children}
          <ThemedToaster />
        </AuthProvider>
      </TooltipProvider>
    </ThemeProvider>
  );
}
