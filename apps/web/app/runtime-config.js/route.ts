import { unstable_noStore as noStore } from "next/cache";

/* The API address, read when the server runs rather than baked in at build time, so changing
 * SHERPA_API_URL only needs a restart. The desktop app's static export keeps its build-time value. */
export function GET() {
  if (process.env.SHERPA_DESKTOP !== "1") noStore();
  const api = process.env.SHERPA_API_URL || process.env.NEXT_PUBLIC_API_URL || "";
  return new Response(`window.__SHERPA_API__=${JSON.stringify(api)};\n`, {
    headers: { "Content-Type": "text/javascript; charset=utf-8", "Cache-Control": "no-store" },
  });
}
