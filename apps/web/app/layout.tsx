import type { Metadata } from "next";
import { Toaster } from "sonner";
import { AuthProvider } from "../lib/auth";
import { SiteHeader } from "../components/site-header";
import "./globals.css";

export const metadata: Metadata = {
  title: "Sherpa — AI Codebase Mentor",
  description: "An agentic onboarding mentor that reads any repo. Every answer cites its code.",
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
      </head>
      <body className="font-sans">
        <AuthProvider>
          <SiteHeader />
          {children}
          <Toaster richColors position="bottom-right" toastOptions={{ style: { fontFamily: "Geist, sans-serif" } }} />
        </AuthProvider>
      </body>
    </html>
  );
}
