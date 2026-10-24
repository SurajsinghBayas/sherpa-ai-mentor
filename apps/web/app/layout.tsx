import type { Metadata, Viewport } from "next";
import { Providers } from "../components/providers";
import { SiteHeader } from "../components/site-header";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Sherpa AI · Your codebase, explained", template: "%s · Sherpa AI" },
  description:
    "Sherpa AI reads a repository and guides you through it: answers, maps and tours that cite the exact file and line they come from.",
  keywords: ["codebase", "AI", "mentor", "developer onboarding", "code understanding"],
  openGraph: {
    title: "Sherpa AI · Your codebase, explained",
    description: "Navigate any codebase with a guide that cites its sources.",
    type: "website",
  },
};

export const viewport: Viewport = {
  viewportFit: "cover", // lets the header paint under the phone's status bar; --safe-top keeps it clear
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#F8F5F0" },
    { media: "(prefers-color-scheme: dark)", color: "#121316" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
        <link rel="preload" as="image" href="/mascot/head.svg" />
        {/* must run before the app's scripts read the API address */}
        {/* eslint-disable-next-line @next/next/no-sync-scripts */}
        <script src="/runtime-config.js" />
      </head>
      <body className="min-h-dvh bg-background font-sans">
        <Providers>
          <SiteHeader />
          {children}
        </Providers>
      </body>
    </html>
  );
}
