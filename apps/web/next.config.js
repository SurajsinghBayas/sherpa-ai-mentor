/** @type {import('next').NextConfig} */
const fs = require("fs");
const path = require("path");

// Voice mode's speech detector (Silero VAD on onnxruntime-web) loads its model, worklet and wasm
// at runtime. Serve them from this app (public/vad, not committed) instead of a CDN, so voice
// also works in the desktop app and offline.
(function copyVadAssets() {
  const dest = path.join(__dirname, "public", "vad");
  const files = [
    ["@ricky0123/vad-web/dist", "vad.worklet.bundle.min.js"],
    ["@ricky0123/vad-web/dist", "silero_vad_v5.onnx"],
    ["onnxruntime-web/dist", "ort-wasm-simd-threaded.wasm"],
    ["onnxruntime-web/dist", "ort-wasm-simd-threaded.mjs"],
  ];
  fs.mkdirSync(dest, { recursive: true });
  for (const [dir, name] of files) {
    const from = path.join(__dirname, "node_modules", dir, name);
    const to = path.join(dest, name);
    try {
      if (!fs.existsSync(to) || fs.statSync(to).size !== fs.statSync(from).size) fs.copyFileSync(from, to);
    } catch (e) {
      console.warn(`voice: couldn't copy ${name} (${e.message}); voice mode falls back to the browser's recognition`);
    }
  }
})();

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(self), geolocation=()" },
  // Google sign-in opens a popup that must be able to message this window back
  { key: "Cross-Origin-Opener-Policy", value: "same-origin-allow-popups" },
];

// The web app reads the API address at runtime from SHERPA_API_URL (see app/runtime-config.js);
// without it, pages call port 8000 on their own host.

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
