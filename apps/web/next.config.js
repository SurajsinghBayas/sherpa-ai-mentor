/** @type {import('next').NextConfig} */
const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  // Google sign-in opens a popup that must be able to message this window back
  { key: "Cross-Origin-Opener-Policy", value: "same-origin-allow-popups" },
];

if (process.env.NODE_ENV === "production" && !process.env.NEXT_PUBLIC_API_URL) {
  console.warn("\n⚠ NEXT_PUBLIC_API_URL is not set: this build will call http://localhost:8000\n");
}

// SHERPA_DESKTOP=1: a static export (out/) for the Tauri app in apps/desktop. Run it through
// `npm run build:desktop`, which builds in a separate copy so a running `next dev` is never disturbed.
const desktop = process.env.SHERPA_DESKTOP === "1";

module.exports = desktop
  ? {
      reactStrictMode: true,
      output: "export",
      images: { unoptimized: true },
    }
  : {
      reactStrictMode: true,
      poweredByHeader: false,
      async headers() {
        return [{ source: "/:path*", headers: securityHeaders }];
      },
    };
