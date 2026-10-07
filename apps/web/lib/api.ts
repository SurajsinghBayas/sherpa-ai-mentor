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

async function req<T>(path: string, opts: RequestInit = {}, auth = true): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (auth) {
    const t = tokenStore.get();
    if (t) headers["Authorization"] = `Bearer ${t}`;
  }
  const r = await fetch(`${API}${path}`, { ...opts, headers: { ...headers, ...(opts.headers || {}) } });
  if (!r.ok) {
    let detail = `${r.status}`;
    try {
      const j = await r.json();
      detail = typeof j?.detail === "string" ? j.detail : JSON.stringify(j?.detail ?? j);
    } catch {
      detail = await r.text();
    }
    throw new ApiError(r.status, detail);
  }
  if (r.status === 204) return undefined as T;
  return r.json() as Promise<T>;
}

export type Citation = { file: string; start_line: number; end_line: number; snippet: string };

export const api = {
  health: () => req<{ ok: boolean; db: string }>("/health", {}, false),
  register: (name: string, email: string, password: string) =>
    req<{ access_token: string }>("/api/auth/register", { method: "POST", body: JSON.stringify({ name, email, password }) }, false),
  login: (email: string, password: string) =>
    req<{ access_token: string }>("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }, false),
  me: () => req<{ id: string; email: string; name: string }>("/api/auth/me"),

  ingest: (repo_url: string) => req<{ repo_id: string; files: number; chunks: number }>("/api/ingest", { method: "POST", body: JSON.stringify({ repo_url }) }, false),
  ask: (repo_id: string, question: string, key_id?: string, endpoint_id?: string) =>
    req<{ answer_markdown: string; citations: Citation[]; confidence: number; verify: { grounded: boolean; unchecked_claims: string[] } }>(
      "/api/ask", { method: "POST", body: JSON.stringify({ repo_id, question, key_id, endpoint_id }) }),
  overview: (repo_id: string) =>
    req<{ summary: string; mermaid: string; components: { name: string; path: string; role: string }[] }>("/api/overview", { method: "POST", body: JSON.stringify({ repo_id }) }, false),
  tour: (repo_id: string, flow: string) =>
    req<{ title: string; estimated_minutes: number; steps: { caption: string; file: string; start_line: number; end_line: number; code: string }[] }>(
      "/api/tours", { method: "POST", body: JSON.stringify({ repo_id, flow }) }, false),
  tasks: (repo_id: string) =>
    req<{ tasks: { title: string; why: string; files: string[]; steps: string[]; difficulty: string }[] }>("/api/tasks", { method: "POST", body: JSON.stringify({ repo_id }) }, false),

  keys: () => req<{ id: string; label: string; provider: string; model: string; last4: string }[]>("/api/keys"),
  addKey: (label: string, provider: string, model: string, api_key: string) =>
    req("/api/keys", { method: "POST", body: JSON.stringify({ label, provider, model, api_key }) }),
  deleteKey: (id: string) => req(`/api/keys/${id}`, { method: "DELETE" }),
  endpoints: () => req<{ id: string; name: string; base_url: string; kind: string; model: string; has_key: boolean }[]>("/api/endpoints"),
  addEndpoint: (name: string, base_url: string, kind: string, model: string, api_key: string) =>
    req("/api/endpoints", { method: "POST", body: JSON.stringify({ name, base_url, kind, model, api_key }) }),
  deleteEndpoint: (id: string) => req(`/api/endpoints/${id}`, { method: "DELETE" }),
  testEndpoint: (name: string, base_url: string, kind: string) =>
    req<{ ok: boolean; status: number | null; hint: string }>("/api/endpoints/test", { method: "POST", body: JSON.stringify({ name, base_url, kind }) }),
};
