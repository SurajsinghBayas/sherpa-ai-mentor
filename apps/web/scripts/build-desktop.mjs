// Static export of the web app for the desktop app (apps/desktop), into out-desktop/.
// It builds in a throwaway copy (.desktop-build/) because `next build` writes into .next/, which a
// running `next dev` is serving from; building in place breaks the dev server's JavaScript.
import { cpSync, existsSync, mkdirSync, rmSync, symlinkSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const web = join(dirname(fileURLToPath(import.meta.url)), "..");
const work = join(web, ".desktop-build");
const out = join(web, "out-desktop");
const SOURCES = [
  "app", "components", "lib", "public", "package.json", "next.config.js", "next-env.d.ts",
  "tailwind.config.ts", "postcss.config.js", "tsconfig.json",
];

rmSync(work, { recursive: true, force: true });
mkdirSync(work);
for (const f of SOURCES) if (existsSync(join(web, f))) cpSync(join(web, f), join(work, f), { recursive: true });
// a junction on Windows: directory symlinks there need admin rights or Developer Mode
symlinkSync(join(web, "node_modules"), join(work, "node_modules"), process.platform === "win32" ? "junction" : "dir");

const api = process.env.SHERPA_API_URL || "http://localhost:8000";
console.log(`Building the desktop export against ${api}`);
// next's JS entry run by this same node: .bin/next is a .cmd shim on Windows, which spawn can't run
const r = spawnSync(process.execPath, [join(web, "node_modules", "next", "dist", "bin", "next"), "build"], {
  cwd: work,
  stdio: "inherit",
  env: { ...process.env, SHERPA_DESKTOP: "1", NEXT_PUBLIC_API_URL: api },
});
if (r.status !== 0) process.exit(r.status ?? 1);

rmSync(out, { recursive: true, force: true });
cpSync(join(work, "out"), out, { recursive: true });
rmSync(work, { recursive: true, force: true });
console.log(`Desktop export ready in ${out}`);
