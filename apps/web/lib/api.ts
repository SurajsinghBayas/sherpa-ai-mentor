// Typed API client — token in localStorage, JSON everywhere, honest errors.

export const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const TOKEN_KEY = "sherpa.jwt";

export const tokenStore = {
  get: () => (typeof window === "undefined" ? null : localStorage.getItem(TOKEN_KEY)),
  set: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function raw(path: string, opts: RequestInit = {}, auth = true): Promise<Response> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (auth) {
    const t = tokenStore.get();
    if (t) headers["Authorization"] = `Bearer ${t}`;
  }
  let r: Response;
  try {
    r = await fetch(`${API}${path}`, { ...opts, headers: { ...headers, ...(opts.headers || {}) } });
  } catch {
    throw new ApiError(0, `Can't reach the Sherpa API at ${API} — is the backend running?`);
  }
  if (r.status === 401 && auth && tokenStore.get() && typeof window !== "undefined") {
    // expired or revoked session: drop the token and send the user to sign in again
    tokenStore.clear();
    window.location.assign("/login");
  }
  if (!r.ok) {
    let detail = `${r.status}`;
    try {
      const j = await r.json();
      detail = typeof j?.detail === "string" ? j.detail : JSON.stringify(j?.detail ?? j);
    } catch {
      detail = (await r.text().catch(() => "")) || detail;
    }
    throw new ApiError(r.status, detail);
  }
  return r;
}

async function req<T>(path: string, opts: RequestInit = {}, auth = true): Promise<T> {
  const r = await raw(path, opts, auth);
  if (r.status === 204) return undefined as T;
  return r.json() as Promise<T>;
}

const post = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });

/* ── types ── */
export type Citation = { file: string; start_line: number; end_line: number; snippet?: string };
export type FileRef = { file: string; start_line: number; end_line: number };
export type Mode = "llm" | "offline";

export type Repo = {
  repo_id: string; name: string; source: string; kind: string; commit: string;
  indexed_at: number | null; files: number; chunks: number; languages: string[]; has_docs: boolean;
  /** private mode: code held in server memory only, wiped at expires_at (epoch seconds) */
  private?: boolean; expires_at?: number | null;
};
export type Changes = { added?: string[]; modified?: string[]; removed?: string[] };

export type AskResponse = {
  answer_markdown: string; citations: Citation[]; confidence: number; mode: Mode; model: string | null;
  verify: { grounded: boolean; verified: number; unchecked_claims: string[] };
};

export type Component = {
  key: string; name: string; layer: string; description: string; files_count: number; key_files: FileRef[];
};
export type Overview = {
  summary: string; components: Component[];
  edges: { from: string; to: string; count: number; from_name: string; to_name: string; example: { file: string; line: number } }[];
  mermaid: string; flows: { name: string; description: string }[];
  start_here: (Citation & { why: string })[];
  entrypoints: { file: string; line: number; why: string }[];
  stats: { files: number; chunks: number; imports: number; languages: string[] };
  citations: Citation[]; mode: Mode; model: string | null;
};

export type TourStep = {
  title: string; caption: string; explanation: string; file: string;
  start_line: number; end_line: number; code: string; language: string;
};
export type Tour = {
  title: string; flow: string; summary: string; estimated_minutes: number;
  steps: TourStep[]; next_questions: string[]; mode: Mode; model: string | null;
};

export type StarterTask = {
  title: string; why: string; difficulty: "easy" | "medium"; estimated_time: string;
  steps: string[]; skills: string[]; files: FileRef[];
};
export type Tasks = { tasks: StarterTask[]; mode: Mode; signals_found: number; model: string | null };

export type DocSection = {
  id: string; title: string; markdown: string; mode: Mode; citations: Citation[];
  stale: boolean; changed_files: string[]; updated_at: number; previous_markdown?: string;
};
export type Docs = {
  repo: string; generated_at: number; sections: DocSection[]; stale_count: number; fresh: boolean;
  changelog: { at: number; event: string; sections: string[]; changed_files: string[] }[];
};
export type SyncResult = Repo & {
  changes: Changes; changed_count: number; full?: boolean; docs_refreshed: string[]; docs: Docs | null;
};
export type CheckResult =
  | { status: "up_to_date"; commit: string; latest: string }
  | { status: "updated"; previous_commit: string; changes: Changes; changed_count: number } & Repo
  | { status: "outdated" | "error"; detail: string; commit: string; latest?: string }
  | { status: "unsupported"; commit: string };

export type UploadManifest = {
  name: string; file_count: number; total_bytes: number;
  languages: { language: string; files: number; bytes: number }[];
  project_types: string[]; entry_points: string[];
  skipped: Record<string, number>; skipped_count: number; skipped_dirs: string[];
  truncated: boolean; top_level: string[];
};
export type UploadStatus = "review" | "queued" | "processing" | "ready" | "failed";
export type UploadJob = {
  job_id: string; repo_id: string; name: string; origin: "zip" | "folder" | "cli";
  status: UploadStatus; stage: string; progress: number; detail: string;
  manifest: UploadManifest | null; attempts: number; can_retry: boolean;
  created_at: number; updated_at: number; finished_at: number | null;
  updates_existing?: boolean;
};

/** POST a ZIP with upload progress (fetch can't report it, XHR can). */
function uploadZip(zip: Blob, filename: string, name: string, origin: "zip" | "folder",
                   onProgress: (fraction: number) => void): Promise<UploadJob> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("file", zip, filename);
    form.append("name", name);
    form.append("origin", origin);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API}/api/uploads`);
    const t = tokenStore.get();
    if (t) xhr.setRequestHeader("Authorization", `Bearer ${t}`);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onerror = () => reject(new ApiError(0, `Can't reach the Sherpa API at ${API}`));
    xhr.onload = () => {
      let body: any = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        /* non-JSON error page */
      }
      if (xhr.status >= 200 && xhr.status < 300) return resolve(body as UploadJob);
      if (xhr.status === 401 && typeof window !== "undefined") {
        tokenStore.clear();
        window.location.assign("/login");
      }
      reject(new ApiError(xhr.status, typeof body?.detail === "string" ? body.detail : `upload failed (${xhr.status})`));
    };
    xhr.send(form);
  });
}

export type StudyTaskId = "architecture" | "flow" | "starter";
export type StudyResult = {
  id: string; participant: string; group: "control" | "sherpa"; task: StudyTaskId; repo: string;
  seconds: number; score: number; max_score: number; useful: number; trustworthy: number;
  reuse: number; notes: string; created_at: string;
};
export type StudySummary = {
  tasks: {
    task: StudyTaskId; title: string; max_score: number; time_saved_pct: number | null;
    control: { n: number; mean_minutes: number | null; median_minutes: number | null; mean_score: number | null };
    sherpa: { n: number; mean_minutes: number | null; median_minutes: number | null; mean_score: number | null };
  }[];
  satisfaction: { useful: number | null; trustworthy: number | null; reuse: number | null };
  participants: { control: number; sherpa: number };
};
export type Health = {
  ok: boolean; db: string; local_ingest: boolean;
  llm: { provider: string; model: string; fallbacks: string[]; available: boolean };
  embeddings: { model: string; available: boolean };
  private_ttl_hours?: number;
};

export const api = {
  health: () => req<Health>("/health", {}, false),
  register: (name: string, email: string, password: string) =>
    req<{ access_token: string }>("/api/auth/register", post({ name, email, password }), false),
  login: (email: string, password: string) =>
    req<{ access_token: string }>("/api/auth/login", post({ email, password }), false),
  me: () => req<{ id: string; email: string; name: string }>("/api/auth/me"),
  authConfig: () =>
    req<{ google_client_id: string | null; email_otp: boolean; password: boolean }>("/api/auth/config", {}, false),
  requestCode: (email: string, purpose: "login" | "signup", name = "") =>
    req<{ sent: boolean; expires_in: number; resend_in: number }>("/api/auth/otp/request", post({ email, purpose, name }), false),
  verifyCode: (email: string, code: string, purpose: "login" | "signup") =>
    req<{ access_token: string }>("/api/auth/otp/verify", post({ email, code, purpose }), false),
  google: (credential: string) => req<{ access_token: string }>("/api/auth/google", post({ credential }), false),

  repos: () => req<{ repos: Repo[] }>("/api/repos"),
  deleteRepo: (repo_id: string) => req(`/api/repos/${repo_id}`, { method: "DELETE" }),
  ingest: (source: { repo_url?: string; local_path?: string; private?: boolean; token?: string }) =>
    req<Repo & { changes: Changes }>("/api/ingest", post(source)),
  sync: (repo_id: string) => req<SyncResult>("/api/sync", post({ repo_id, refresh_docs: true })),
  /** Manual "Reindex": rebuild the whole index from the source (docs are left to the Docs tab). */
  reindex: (repo_id: string) => req<SyncResult>("/api/sync", post({ repo_id, full: true, refresh_docs: false })),
  /** Automatic: new commit upstream → re-index only the changed files; cheap when unchanged. */
  uploadZip,
  startUpload: (job_id: string) => req<UploadJob>(`/api/uploads/${job_id}/start`, { method: "POST" }),
  upload: (job_id: string) => req<UploadJob>(`/api/uploads/${job_id}`),
  uploads: () => req<{ uploads: UploadJob[] }>("/api/uploads"),
  discardUpload: (job_id: string) => req(`/api/uploads/${job_id}`, { method: "DELETE" }),
  checkUpdates: (repo_id: string) => req<CheckResult>(`/api/repos/${encodeURIComponent(repo_id)}/check`, { method: "POST" }),
  file: (repo_id: string, path: string) =>
    req<{ path: string; lines: string[]; total: number; language: string }>(
      `/api/file?repo_id=${encodeURIComponent(repo_id)}&path=${encodeURIComponent(path)}`),

  /** `spoken`: a short conversational answer meant to be heard (voice mode). */
  ask: (repo_id: string, question: string, history: { role: string; text: string }[] = [], spoken = false) =>
    req<AskResponse>("/api/ask", post({ repo_id, question, history, spoken })),
  overview: (repo_id: string, refresh = false) => req<Overview>("/api/overview", post({ repo_id, refresh })),
  tour: (repo_id: string, flow: string) => req<Tour>("/api/tours", post({ repo_id, flow })),
  tasks: (repo_id: string, refresh = false) => req<Tasks>("/api/tasks", post({ repo_id, refresh })),

  docs: (repo_id: string) => req<Docs>(`/api/docs/${repo_id}`),
  generateDocs: (repo_id: string) => req<Docs>("/api/docs/generate", post({ repo_id })),
  refreshDocs: (repo_id: string) => req<Docs>("/api/docs/refresh", post({ repo_id })),
  docsMarkdown: async (repo_id: string) => (await raw(`/api/docs/${repo_id}/markdown`)).text(),

  voiceConfig: () =>
    req<{ provider: "polly" | "browser"; voice: string | null; max_chars: number; stt: "transcribe" | "browser" }>(
      "/api/voice/config"
    ),
  /** MP3 from Amazon Polly; 503 when the API has no AWS credentials (callers fall back to the browser voice). */
  speak: async (text: string) => (await raw("/api/voice/speak", post({ text }))).blob(),

  studyProtocol: () =>
    req<{ tasks: Record<StudyTaskId, { title: string; prompt: string; max_score: number }>; rubric: string }>(
      "/api/study/protocol", {}, false),
  studyResults: () => req<StudyResult[]>("/api/study/results"),
  studySummary: () => req<StudySummary>("/api/study/summary"),
  addStudyResult: (body: Omit<StudyResult, "id" | "max_score" | "created_at">) =>
    req<StudyResult>("/api/study/results", post(body)),
  deleteStudyResult: (id: string) => req(`/api/study/results/${id}`, { method: "DELETE" }),
  studyCsv: async () => (await raw("/api/study/results.csv")).text(),

  keys: () => req<{ id: string; label: string; provider: string; model: string; last4: string }[]>("/api/keys"),
  addKey: (label: string, provider: string, model: string, api_key: string) =>
    req("/api/keys", post({ label, provider, model, api_key })),
  deleteKey: (id: string) => req(`/api/keys/${id}`, { method: "DELETE" }),
  endpoints: () => req<{ id: string; name: string; base_url: string; kind: string; model: string; has_key: boolean }[]>("/api/endpoints"),
  addEndpoint: (name: string, base_url: string, kind: string, model: string, api_key: string) =>
    req("/api/endpoints", post({ name, base_url, kind, model, api_key })),
  deleteEndpoint: (id: string) => req(`/api/endpoints/${id}`, { method: "DELETE" }),
  testEndpoint: (name: string, base_url: string, kind: string, api_key = "") =>
    req<{ ok: boolean; status: number | null; hint: string }>("/api/endpoints/test", post({ name, base_url, kind, api_key })),
};
