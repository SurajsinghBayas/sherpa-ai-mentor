# API reference

The web app, desktop app and CLI all use this HTTP API. Interactive docs are at `/api/docs` when `ENVIRONMENT` isn't `production`.

Every `/api/*` route except sign-up/login and the study protocol needs a signed-in user. Repos belong to the user who indexed them; other users get 404. AI calls count against a daily per-user quota (429 when used up).

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/ingest` | Index `{repo_url}` (https, GitHub/GitLab/Bitbucket) or `{local_path}` (dev only). Re-indexing reports added/modified/removed files. |
| `GET` · `DELETE` | `/api/repos` · `/api/repos/{repo_id}` | Your indexed repositories · delete one with its index and docs |
| `POST` | `/api/ask` | `{repo_id, question, history?}` → markdown answer + verified citations, `mode` (`llm`/`offline`), `model` |
| `POST` | `/api/overview` | Components, import edges, Mermaid, flows, start-here files (cached per snapshot; `refresh` to regenerate) |
| `POST` | `/api/tours` | `{repo_id, flow}` → ordered steps with code and explanations |
| `POST` | `/api/tasks` | Starter tasks grounded in code signals |
| `POST` | `/api/docs/generate` · `/api/docs/refresh` | Create the onboarding guide · rewrite stale sections |
| `GET` | `/api/docs/{repo_id}` · `/markdown` | Guide with per-section stale status · Markdown export |
| `GET` | `/cli/sherpa.py` | The CLI, preset to this API (public) |
| `POST` | `/api/uploads` | Multipart `file` (a `.zip`) + `name`, `origin` → job in `review` with a manifest (nothing indexed yet) |
| `POST` · `GET` · `DELETE` | `/api/uploads/{job_id}[/start]` | Start (or retry) indexing · poll status/stage/progress · discard; `GET /api/uploads` lists your jobs |
| `POST` | `/api/repos/{repo_id}/check` | Automatic re-index: compares the indexed commit with the remote's latest (`git ls-remote`, no clone, no quota). If it moved, only added/modified/removed files are re-chunked, re-embedded and rewritten → `up_to_date` · `updated` (+ `changes`) · `outdated` (busy/out of quota) · `error` |
| `POST` | `/api/sync` | Re-index from source and refresh stale doc sections; `full: true` rebuilds the whole index (the **Reindex** button) |
| `GET` | `/api/file` | Full text of a snapshot file (backs the citation viewer) |
| `POST` | `/api/freshness` | Check *your own* docs for dead file references and headings with no matching code |
| `*` | `/api/study/*` | User-study protocol, results, summary and CSV (auth required) |
| `POST` | `/api/auth/otp/request` · `/api/auth/otp/verify` | Email a 6-digit code (10 min, 5 tries, 1/min, 5/hour) · exchange it for a session |
| `POST` | `/api/auth/google` | Sign in or sign up with a Google ID token |
| `*` | `/api/auth/*`, `/api/keys`, `/api/endpoints` | Password accounts, auth config, and bring-your-own LLM credentials (Fernet-encrypted) |

### Private mode

`POST /api/ingest` also takes `private: true` and an optional `token` (a read-only access token for a private repository). A private repo's code, chunks, vectors and generated outputs stay in the API's memory only and expire after `PRIVATE_TTL_HOURS`; requests after that return `410`. The token is used for that one clone and never stored or logged. Private repos aren't synced or auto-checked: import again to pick up changes.

## Keeping the index current

- **Automatic:** when a repo is opened, when you return to the tab, and every 5 minutes while it's open, the web app calls `/api/repos/{id}/check`. The API compares the indexed commit with the branch's latest commit (one `git ls-remote`; checks within 60 s reuse the answer). If it changed, it clones, diffs file hashes, and rewrites only the changed files' rows; unchanged files keep their chunks and embeddings. Overview and starter tasks are recomputed; doc sections whose sources changed show as stale. Local folders (dev) are compared by file hashes instead.
- **Manual:** the **Reindex** button in the repo bar rebuilds the entire index from the latest code (`/api/sync` with `full: true`). Embeddings are still reused for chunks whose text didn't change, so a rebuild costs little.
