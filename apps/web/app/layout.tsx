import type { Metadata } from "next";
import { Toaster } from "sonner";
import { AuthProvider } from "../lib/auth";
import { SiteHeader } from "../components/site-header";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Sherpa — AI Codebase Mentor", template: "%s — Sherpa" },
  description:
    "Sherpa reads any GitHub repo and guides you with grounded answers — every claim cites its exact file and line.",
  keywords: ["codebase", "AI", "mentor", "developer onboarding", "code understanding"],
  openGraph: {
    title: "Sherpa — AI Codebase Mentor",
    description: "Understand any codebase, immediately.",
    type: "website",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600;700&family=Geist+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="font-sans min-h-screen bg-background">
        <AuthProvider>
          <SiteHeader />
          {children}
          <Toaster
            richColors
            position="bottom-right"
            toastOptions={{
              style: { fontFamily: "Geist, sans-serif", borderRadius: "0.75rem" },
            }}
          />
        </AuthProvider>
      </body>
    </html>
  );
}
