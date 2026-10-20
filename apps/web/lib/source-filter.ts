// Client-side mirror of the API's file filter (services/api/app/ingest.py → skip_reason).
// Used for folder uploads so node_modules, .git, build output, secrets and binaries never
// leave the user's machine. The server filters again; this only saves the upload.

const IGNORE_DIRS = new Set([
  ".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next", ".turbo",
  "coverage", ".pytest_cache", "vendor", "bower_components", "target", ".gradle", ".idea",
  ".mypy_cache", ".ruff_cache", ".tox", ".nuxt", ".svelte-kit", ".parcel-cache", ".terraform",
  "__MACOSX", ".hg", ".svn",
]);
const SECRET_EXT = new Set([".pem", ".key", ".p12", ".pfx", ".keystore", ".jks"]);
const IGNORE_EXT = new Set([
  ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".woff2", ".ttf", ".eot", ".mp4", ".pdf",
  ".zip", ".lock", ".db", ".sqlite", ".sqlite3", ".tsbuildinfo", ".class", ".jar", ".war", ".o", ".so",
  ".dll", ".exe", ".dylib", ".a", ".wasm", ".pyc", ".map", ".bin", ".dat", ".mp3", ".wav", ".webp",
  ".avif", ".bmp", ".tiff", ".psd", ".gz", ".tar", ".tgz", ".7z", ".rar", ".bz2", ".xz", ".iso", ".dmg",
  ".pkl", ".pt", ".onnx", ".h5", ".parquet", ".npy", ...SECRET_EXT,
]);
const SECRET_FILES = new Set(["id_rsa", "id_ed25519", ".npmrc", ".pypirc", ".netrc"]);
const IGNORE_FILES = new Set([".DS_Store", "package-lock.json", "pnpm-lock.yaml", ...SECRET_FILES]);
const ENV_TEMPLATES = [".example", ".sample", ".template", ".dist"];
export const MAX_FILE_BYTES = 400_000;

export type SkipReason = "generated" | "secret" | "binary" | "too large";

export function skipReason(path: string, size = 0): SkipReason | null {
  const parts = path.split("/");
  const name = parts[parts.length - 1];
  if (parts.slice(0, -1).some((p) => IGNORE_DIRS.has(p))) return "generated";
  if (IGNORE_FILES.has(name) || name.startsWith("._")) return SECRET_FILES.has(name) ? "secret" : "generated";
  if ((name.startsWith(".env") || name.endsWith(".env")) && !ENV_TEMPLATES.some((t) => name.endsWith(t)))
    return "secret";
  if (name.endsWith(".min.js") || name.endsWith(".min.css")) return "generated";
  const dot = name.lastIndexOf(".");
  const ext = dot > 0 ? name.slice(dot).toLowerCase() : "";
  if (IGNORE_EXT.has(ext)) return SECRET_EXT.has(ext) ? "secret" : "binary";
  if (size > MAX_FILE_BYTES) return "too large";
  return null;
}

const MARKERS: [string, string][] = [
  ["package.json", "Node.js"], ["tsconfig.json", "TypeScript"], ["next.config.js", "Next.js"],
  ["next.config.mjs", "Next.js"], ["next.config.ts", "Next.js"], ["requirements.txt", "Python"],
  ["pyproject.toml", "Python"], ["manage.py", "Django"], ["pom.xml", "Java (Maven)"],
  ["build.gradle", "Java/Kotlin (Gradle)"], ["go.mod", "Go"], ["Cargo.toml", "Rust"], ["Gemfile", "Ruby"],
  ["composer.json", "PHP"], ["pubspec.yaml", "Flutter/Dart"], ["Dockerfile", "Docker"],
];

export type FolderPlan = {
  name: string;
  files: { path: string; file: File }[];
  totalBytes: number;
  skipped: Partial<Record<SkipReason, number>>;
  skippedDirs: string[];
  projectTypes: string[];
};

/** Decide what to upload from a directory picker's FileList (paths keep their hierarchy). */
export function planFolder(list: FileList | File[]): FolderPlan {
  const files: FolderPlan["files"] = [];
  const skipped: FolderPlan["skipped"] = {};
  const dirs = new Map<string, number>();
  let name = "";
  for (const file of Array.from(list)) {
    const path = (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name;
    name ||= path.includes("/") ? path.split("/")[0] : "";
    const why = skipReason(path, file.size);
    if (why) {
      skipped[why] = (skipped[why] || 0) + 1;
      if (why === "generated") {
        const d = path.split("/").slice(0, -1).find((p) => IGNORE_DIRS.has(p));
        if (d) dirs.set(d + "/", (dirs.get(d + "/") || 0) + 1);
      }
      continue;
    }
    if (file.size === 0) continue;
    files.push({ path, file });
  }
  const paths = files.map((f) => f.path.split("/").slice(1).join("/") || f.path);
  const projectTypes = [...new Set(MARKERS.filter(([m]) => paths.some((p) => p === m || p.endsWith("/" + m))).map(([, t]) => t))];
  return {
    name: name || "project",
    files,
    totalBytes: files.reduce((n, f) => n + f.file.size, 0),
    skipped,
    skippedDirs: [...dirs.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6).map(([d]) => d),
    projectTypes,
  };
}

/** Zip the planned files in a worker (fflate), keeping each file's relative path.
 *  `onProgress` goes 0 → 0.85 while files are read, then 1 when compression is done. */
export async function zipFolder(plan: FolderPlan, onProgress?: (fraction: number) => void): Promise<Blob> {
  const { zip } = await import("fflate");
  const entries: Record<string, Uint8Array> = {};
  let done = 0;
  for (const { path, file } of plan.files) {
    entries[path] = new Uint8Array(await file.arrayBuffer());
    onProgress?.((0.85 * ++done) / plan.files.length);
  }
  const data = await new Promise<Uint8Array>((resolve, reject) =>
    zip(entries, { level: 6 }, (err, out) => (err ? reject(err) : resolve(out)))
  );
  onProgress?.(1);
  return new Blob([data], { type: "application/zip" });
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(n < 10 * 1024 ? 1 : 0)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}
