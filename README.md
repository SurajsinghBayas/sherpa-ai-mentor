<div align="center">

<br />

<img src="https://img.shields.io/badge/Sherpa-AI%20Codebase%20Mentor-0a0a0a?style=for-the-badge&labelColor=0a0a0a&color=4a9eff" alt="Sherpa" />

<br /><br />

**An AI mentor that reads a repository and helps a newcomer understand it fast. Every answer cites the exact code it relies on.**

Built for CODE APEX 3.0 · iMocha track · Problem statement **IM-05 — Codebase Mentor: AI Onboarding for Developers**.

[![CI](https://github.com/SurajsinghBayas/sherpa-ai-mentor/actions/workflows/ci.yml/badge.svg)](https://github.com/SurajsinghBayas/sherpa-ai-mentor/actions/workflows/ci.yml)
![License](https://img.shields.io/badge/license-MIT-22c55e?style=flat)
![Next.js](https://img.shields.io/badge/Next.js-14-black?style=flat&logo=next.js)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat&logo=fastapi)

</div>

---

## What it does (mapped to IM-05)

| IM-05 asks for | Sherpa | Where |
|---|---|---|
| Architecture overview: main parts and how they connect | Resolves the **real import graph** (Python + JS/TS), groups files into components, draws a Mermaid map with import counts, and explains each part with citations. Also lists key flows and "start reading here" files. | **Architecture** tab · `POST /api/overview` |
| Guided tours of key flows ("what happens when a user signs up") | Retrieves candidate code plus one hop along the import graph, then orders the stops in **execution order** (UI → API → logic → data). Each step shows line-numbered code and an explanation. | **Code Tours** tab · `POST /api/tours` |
| How/why answers linked to exact files and lines | Grounded Q&A with follow-up context. Every `[file:12-30]` becomes a chip that opens the cited lines in a code viewer. | **Ask Sherpa** tab · `POST /api/ask` |
| Suggested starter tasks | Static analysis finds TODO/FIXMEs, untested modules, long functions and missing docs. The model turns the best into first-PR tasks with steps, effort and exact files. | **Starter Tasks** tab · `POST /api/tasks` |
| *Optional:* docs that stay up to date as the code changes | **Living docs**: an onboarding guide where each section records the hashes of the files it cites. **Sync with code** re-indexes, flags only the sections whose sources changed, and rewrites them. A changelog and the previous version are kept. | **Living Docs** tab · `POST /api/sync`, `/api/docs/*` |
| Works on a real open-source repo | Demo repo: [`fastapi/full-stack-fastapi-template`](https://github.com/fastapi/full-stack-fastapi-template) (219 files, FastAPI + React). Any public GitHub/GitLab/Bitbucket repo works. | |
| Every answer cites code so it can be checked | The **CitationVerifier** checks every citation against the snapshot, normalises short paths, and removes any that don't exist. The UI shows how many were verified. | `agents/common.py` |
| Small peer test showing newcomers get faster | Built-in **user-study tool**: timed tasks for a control group (repo only) and a Sherpa group, scored against a rubric, with an aggregated chart and CSV export. | **User study** page · `/api/study/*` |

## How answers stay grounded

```
question ─▶ alias expansion ─▶ hybrid retrieval (pgvector embeddings + keyword, tests demoted)
        ─▶ +1 hop along the import graph ─▶ LLM (context headers carry file:start-end)
        ─▶ CitationVerifier ─▶ answer with only verified [file:L1-L2] citations
```

1. **Provenance-first chunks.** Every chunk carries `file:start-end`. Python is split on `def`/`class` via `ast`, and other files by blocks. Chunks are embedded with Amazon Nova embeddings and stored in Postgres with pgvector, keyed by content hash so unchanged code is never re-embedded. Without Postgres or a Bedrock key, search falls back to TF-IDF (logged).
2. **The model can only cite what it was shown.** Prompts list each chunk under a `--- path:start-end ---` header. Tours and tasks go further: the model picks from numbered candidates (`C3`, `T2`), so a step can never point at invented code.
3. **The verifier is the gate.** Each citation must resolve to a real file, with a line range inside it. Ghost citations are removed from the text, and combined ones (`[a.py:1-5, 9-12]`) are split. If an answer has no valid citations, the model gets one retry. If it still has none, the answer is labelled unconfirmed.
4. **Secrets never reach the model.** Ingest skips `.env*` files (templates like `.env.example` are kept), databases, keys, lockfiles and binaries.

## Model choice

The default LLM is **Kimi K2.5** (`moonshotai.kimi-k2.5`) on AWS Bedrock Mantle (OpenAI-compatible), so no user key is needed. We benchmarked the models available on that endpoint with grounded questions over the same repo:

| Model | Avg latency | Valid citations (3 Qs) | Notes |
|---|---|---|---|
| **moonshotai.kimi-k2.5** ✅ | 2.8 s | **18** | Best-structured answers (direct answer → evidence → try next); JSON valid 3/3 |
| qwen.qwen3-coder-480b-a35b-instruct | 2.2 s | 11 | Fastest; plainer formatting. **First fallback** |
| zai.glm-4.7 | 2.7 s | 13 | Good, slightly less structured |
| deepseek.v3.2 (previous default) | 3.7 s | 14 | **Second fallback** |
| mistral.devstral-2-123b | 5.4 s | 15 | Slowest |
| anthropic.claude-sonnet-5 | — | — | Listed, but returns 404 on this endpoint with these credentials |

If the main model errors, Sherpa tries `LLM_FALLBACK_MODELS` in order. If they all fail, an extractive offline composer answers from the retrieved code. **Every fallback is logged** and the UI labels offline answers. Users can also bring their own OpenAI, Anthropic, Gemini or OpenRouter key, or any OpenAI-compatible or Ollama endpoint (Settings → Keys).

## Results

**Automated grounding eval** ([`evals/results.md`](evals/results.md)). This is 10 maintainer-style questions on the demo repo with Kimi K2.5, one run each:

| Metric | pgvector (Nova embeddings, AWS RDS) | TF-IDF (previous) |
|---|---|---|
| Citation validity (cited lines exist in the repo) | **97%** (2 bad citations removed by the verifier) | 98% |
| Answers with ≥ 1 verified citation | **10 / 10** | 10 / 10 |
| Cites the file a maintainer would point to | **10 / 10** | 9 / 10 |
| Median latency | 4.6 s | 3.3 s |

Embeddings add one Bedrock call and one database query per question, which explains most of the extra latency.

**User study.** The protocol and recording tool are in the app (**User study** page; see [`evals/user_study.md`](evals/user_study.md)). Results come from real participants and aren't fabricated here: run the sessions, then export the CSV and chart.

## Quickstart

```bash
# 1. backend  (Python 3.11+)
cp .env.example .env            # add OPENAI_API_KEY for Bedrock Mantle (or leave blank for offline mode)
cd services/api && pip install -r requirements.txt && cd ../..
make api                         # → http://localhost:8000  (API docs at /api/docs)

# 2. frontend
cd apps/web && npm install && npm run dev   # → http://localhost:3000
```

Sign up, paste `https://github.com/fastapi/full-stack-fastapi-template`, and click **Index repo** (the first index embeds every chunk, about 40 s; re-indexing reuses them). Then open **Architecture**.

`make api` sets `ALLOW_LOCAL_INGEST=true`, so you can also index a folder on your machine. That's the easiest way to demo living docs: edit a file, then click **Sync with code**. Keep this off on shared servers.

Full stack in Docker: `docker compose up --build` (api :8000, web :3000, Postgres with pgvector).

## Bringing in code

**Add repo** offers three sources:

| Source | How it works |
|---|---|
| **GitHub** | Paste a public GitHub/GitLab/Bitbucket URL. Kept current automatically (see below). |
| **Upload ZIP** | Drop a `.zip` (≤ 100 MB). The API reads it in memory, never extracting to disk: absolute paths, `..`, symlinks and encrypted entries are skipped and every read is size-capped (zip-bomb safe). |
| **Local folder** | Pick a folder. The browser filters it first, so `node_modules`, `.git`, build output, secrets and binaries never leave the machine, shows the project name, file count, size and type, then zips and uploads the rest. |

Uploads then show a **review** from the server: project type (Node.js, Python, Java, Go, Docker …), languages, likely entry points, and what was skipped and why. **Start indexing** runs a background job (`queued → processing → ready | failed`) with live progress; you can leave the page. A failed job can be **retried** without uploading again (the accepted files are kept for 24 h). Uploading the same project name again updates it in place and re-indexes only changed files. Each upload is scoped to its owner like any repo.

Kept: source, `package.json`, `requirements.txt`, `pyproject.toml`, `pom.xml`, `Dockerfile`, CI and other config, `.env.example`. Skipped: dependencies and build output (`node_modules/`, `.git/`, `dist/`, `build/`, `.next/`, `coverage/`, `vendor/`, `target/` …), lockfiles, minified bundles, binaries and media, files over 400 KB, `.env` files and private keys.

### CLI

```bash
curl -fsSL <API>/cli/sherpa.py -o ~/.local/bin/sherpa && chmod +x ~/.local/bin/sherpa   # or: pipx install ./cli
sherpa login --api https://api.your-sherpa.app    # emails you a sign-in code (--password also works)
sherpa upload ./my-project  # pack → review → index, with a progress bar
sherpa ask <repo_id> "How does signup work?"
sherpa status | repos | retry <job_id> | logout
```

Inside a git checkout the CLI sends only files git tracks or would track (so `.gitignore` is respected), applies the same filters, never follows symlinks, and re-uploading the same `--name` updates the project. The web app has the same guide, with commands filled in for your server, at `/cli` and under **Add repo → CLI** (which also shows CLI uploads live). After editing `cli/sherpa_cli.py`, run `make cli-sync` so the API serves the new version (a test fails until you do). Full guide: [`cli/README.md`](cli/README.md) (install, sign-in, options, CI use, limits, troubleshooting).

## Desktop app (macOS)

The same web app, packaged as a native window with [Tauri 2](https://tauri.app) in `apps/desktop`. One codebase: Tauri bundles a static export of `apps/web`, which calls the API over HTTP like the browser does.

```bash
make api              # the desktop app talks to http://localhost:8000 for now
make desktop          # dev window with hot reload (reuses `make web` on :3000 if it is running)
make desktop-build    # → apps/desktop/src-tauri/target/release/bundle/{macos/Sherpa AI.app, dmg/Sherpa AI_0.1.0_aarch64.dmg}
```

Needs Rust (`rustup`) and the Xcode command-line tools. Point a build at another API with `SHERPA_API_URL=https://api.your-sherpa.app make desktop-build`. Details, the production checklist and Windows notes: [`apps/desktop/README.md`](apps/desktop/README.md).

## Deploying

- **Database:** AWS RDS for PostgreSQL (15.2+ has pgvector; ours is 18.3). Migrations run on API startup and enable the extension. See [`docs/rds_setup.md`](docs/rds_setup.md).
- **API:** any container host (Railway, Render, Fly, App Runner) using `services/api/Dockerfile`. It listens on `$PORT`. Set `ENVIRONMENT=production`; the API then refuses to start with a weak `JWT_SECRET_KEY`, a missing or invalid `ENCRYPTION_KEY`, SQLite or SSL-disabled `DATABASE_URL`, `ALLOW_LOCAL_INGEST=true`, or non-https `ALLOWED_ORIGINS`. Point the load balancer's health check at `GET /ready` (503 until the database answers); `/health` is liveness.
- **Web:** Vercel (root `apps/web`) or `apps/web/Dockerfile`. Set `NEXT_PUBLIC_API_URL` to the API's URL at build time, and add the web origin to the API's `ALLOWED_ORIGINS`.
- **Secrets** (`OPENAI_API_KEY`, `AWS_BEARER_TOKEN_BEDROCK`, `JWT_SECRET_KEY`, `ENCRYPTION_KEY`, `DATABASE_URL`) go in the host's secret settings, never in the repo.

## API

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

## Keeping the index current

- **Automatic:** when a repo is opened, when you return to the tab, and every 5 minutes while it's open, the web app calls `/api/repos/{id}/check`. The API compares the indexed commit with the branch's latest commit (one `git ls-remote`; checks within 60 s reuse the answer). If it changed, it clones, diffs file hashes, and rewrites only the changed files' rows; unchanged files keep their chunks and embeddings. Overview and starter tasks are recomputed; doc sections whose sources changed show as stale. Local folders (dev) are compared by file hashes instead.
- **Manual:** the **Reindex** button in the repo bar rebuilds the entire index from the latest code (`/api/sync` with `full: true`). Embeddings are still reused for chunks whose text didn't change, so a rebuild costs little.

## Production guardrails

| Risk | Guardrail |
|---|---|
| Unsafe config | `ENVIRONMENT=production` refuses to start on weak/invalid secrets, SQLite, SSL off, `*` or http origins, local ingest on; warns when no email/Google sign-in or no embeddings |
| Password guessing, sign-up spam, mail-bombing via our Gmail | Per-IP limits on every `/api/auth/*` route (login 10/min + 20 per account per 15 min, codes 5/min and 20/hour, sign-up 5/min), plus the per-email code throttle; 429 with `Retry-After` |
| API abuse and cost | Per-user rate limit per endpoint, daily LLM/ingest quotas (row-locked so parallel calls can't overshoot), repo cap, 1 MB body limit (chunked uploads too), question/flow length caps, `LLM_TIMEOUT_SECONDS` per model call |
| SSRF | Repo URLs: https on GitHub/GitLab/Bitbucket only, normalised, no credentials/ports/odd paths, branch names can't become git options. Custom LLM endpoints: in production https and public IPs only (checked on save, on test and on every use), no redirects |
| Malicious repositories | Hardened clone (no prompts, hooks, submodules, LFS or non-https transports; size and time caps; temp dir always removed); symlinks are never followed, so a repo can't make the API read server files; secrets, keys and databases are never indexed |
| Overload | At most `MAX_CONCURRENT_INGESTS` clones per instance (503 "busy") and one per user (409) |
| Prompt injection | Repository text is treated as untrusted data in the system prompt; answers keep only citations that verify against the indexed code |
| Data exposure | Owner-scoped repos (others get 404), `Cache-Control: no-store` on `/api/*`, API docs hidden in production, security headers on API and web, no tracebacks to clients (500s carry an `X-Request-ID` that matches the server log), email codes never logged in production |

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `ENVIRONMENT` | `development` | `production` enables the startup safety checks |
| `LLM_PROVIDER` | `none` | `openai` (any OpenAI-compatible gateway) · `openrouter` · `anthropic` · `gemini` · `ollama` |
| `LLM_MODEL` | `moonshotai.kimi-k2.5` when provider is `openai` | |
| `LLM_FALLBACK_MODELS` | `qwen.qwen3-coder-480b-a35b-instruct,deepseek.v3.2` | Tried in order; each fallback is logged |
| `OPENAI_API_KEY` / `OPENAI_BASE_URL` | — | e.g. `https://bedrock-mantle.ap-south-1.api.aws/v1` |
| `JWT_SECRET_KEY` | dev value | Set a long random value in production |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `MAIL_FROM_NAME` | — / 587 / — / — / `Sherpa AI` | Email sign-in codes (Gmail app password works) |
| `GOOGLE_CLIENT_ID` | — | Google sign-in (OAuth client, Web application); button hidden when blank |
| `DATABASE_URL` | SQLite | AWS RDS Postgres in production (see `docs/rds_setup.md`); holds accounts, repos, chunks and embeddings |
| `AWS_BEARER_TOKEN_BEDROCK` | — | Bedrock API key for embeddings; blank → TF-IDF search |
| `AWS_DEFAULT_REGION` / `EMBEDDING_MODEL` | `us-east-1` / `amazon.nova-2-multimodal-embeddings-v1:0` | |
| `DAILY_LLM_REQUESTS` / `DAILY_INGESTS` / `MAX_REPOS_PER_USER` | 300 / 30 / 15 | Per-user quotas |
| `ENCRYPTION_KEY` | derived | Fernet key for stored user API keys |
| `ALLOW_LOCAL_INGEST` | `false` | Lets the API read server folders; local dev only |
| `ALLOWED_ORIGINS` | `http://localhost:3000` | CORS |
| `RATE_LIMIT_PER_MINUTE` / `MAX_BODY_BYTES` | 60 / 1 MB | Per user per endpoint · request size |
| `MAX_CONCURRENT_INGESTS` / `MAX_REPO_MB` / `CLONE_TIMEOUT_SECONDS` | 3 / 500 / 180 | Ingest limits |
| `LLM_TIMEOUT_SECONDS` | 90 | Per model call |
| `MAX_UPLOAD_MB` / `MAX_UPLOAD_SOURCE_MB` | 100 / 50 | Uploaded ZIP size · text kept after filtering |
| `LOG_LEVEL` | `INFO` | Fallbacks log at `WARNING` |

## Project layout

```
services/api/app/
  main.py            routes, middleware (CORS, request id, body limit, security headers), ingest slots
  guards.py          rate limiter, SSRF checks for outbound URLs, git URL/branch validation
  uploads.py         safe in-memory ZIP reading, manifest, background ingestion jobs
  prompts/system.md  mentor system prompt (persona, grounding and safety rules)
  llm.py             LLM client: default model + fallback chain + BYOK, JSON parsing
  ingest.py          clone/walk, secret & binary filtering, snapshot metadata
  chunk.py           provenance-preserving chunker
  store.py           RepoStore: hybrid search, full-text file access (backend-agnostic)
  persist.py         SQL backend: snapshots in Postgres/SQLite, pgvector search, embedding reuse
  embeddings.py      Amazon Bedrock Nova embeddings client
migrations/          Alembic schema migrations (run on startup)
  retrieval.py       newcomer phrasing → code vocabulary
  analysis.py        import graph, components, entrypoints, symbols, task signals
  agents/            common (verifier) · mentor (Q&A) · overview · tour · tasks · docs (living docs)
  routers/           auth · keys (BYOK) · study (user study) · uploads
apps/web/
  components/workspace/   one panel per feature + shared UI
  components/markdown.tsx citation-aware Markdown renderer
  components/code-viewer.tsx  drawer that opens cited lines
  components/study.tsx    user-study recorder
evals/               golden questions, eval runner, results, study protocol
cli/                 `sherpa` command: login, upload a folder, ask (stdlib only)
apps/desktop/        Tauri 2 shell that packages apps/web as a macOS app (Windows later)
```

## Tests

`make test` runs 67 backend tests: citation verification, import graph, living-docs staleness, LLM fallback chain, ingest safety, repo ownership, quotas, migrations, email codes, Google sign-in, tour call-following, production config checks, study API, and the production guardrails (SSRF, symlinks, git URL/branch validation, rate limits, ingest slots, body limits) re-indexing (commit check, incremental vs full) and uploads (hostile ZIP entries, size caps, review → index, re-upload, retry, stale jobs, privacy). They run offline and never call a paid model. `make eval` runs the live grounding eval. CI also builds the web app.

## Tools, models and credits

- **AI used to build this:** Claude Code (Anthropic, Claude Opus) helped write and review code. At runtime, Sherpa uses Kimi K2.5 / Qwen3-Coder / DeepSeek V3.2 via AWS Bedrock Mantle, and Amazon Nova multimodal embeddings via Amazon Bedrock.
- **Open-source libraries:** FastAPI, Pydantic, SQLAlchemy, Alembic, pgvector, scikit-learn (TF-IDF), OpenAI Python SDK, PyJWT, passlib, cryptography, httpx; Next.js, React, Tailwind CSS, Framer Motion, lucide-react, sonner, react-markdown, remark-gfm, Mermaid.
- **Demo repository:** [fastapi/full-stack-fastapi-template](https://github.com/fastapi/full-stack-fastapi-template) (MIT).
- Only public code and pseudonymous study data are used. No API keys are committed.

## License

MIT, see [`LICENSE`](LICENSE).
