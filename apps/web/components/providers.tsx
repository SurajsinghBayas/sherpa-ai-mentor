"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { ThemeProvider, useTheme } from "next-themes";
import { Toaster } from "sonner";
import { AuthProvider } from "../lib/auth";
import { isDesktop } from "../lib/desktop";
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

/** Desktop app only: the marketing page goes straight to the workspace, and links to other sites open
 *  in the default browser instead of replacing the app's window. */
function DesktopShell() {
  const path = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (isDesktop() && path === "/") router.replace("/dashboard");
  }, [path, router]);

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
          <DesktopShell />
          {children}
          <ThemedToaster />
        </AuthProvider>
      </TooltipProvider>
    </ThemeProvider>
  );
}
