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

## Deploying

- **Database:** AWS RDS for PostgreSQL (15.2+ has pgvector; ours is 18.3). Migrations run on API startup and enable the extension. See [`docs/rds_setup.md`](docs/rds_setup.md).
- **API:** any container host (Railway, Render, Fly, App Runner) using `services/api/Dockerfile`. It listens on `$PORT`. Set `ENVIRONMENT=production`; the API then refuses to start with a weak `JWT_SECRET_KEY`, no `ENCRYPTION_KEY`, no `DATABASE_URL`, `ALLOW_LOCAL_INGEST=true` or `ALLOWED_ORIGINS=*`.
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
| `POST` | `/api/sync` | Re-index from source, diff, and refresh stale doc sections |
| `GET` | `/api/file` | Full text of a snapshot file (backs the citation viewer) |
| `POST` | `/api/freshness` | Check *your own* docs for dead file references and headings with no matching code |
| `*` | `/api/study/*` | User-study protocol, results, summary and CSV (auth required) |
| `POST` | `/api/auth/otp/request` · `/api/auth/otp/verify` | Email a 6-digit code (10 min, 5 tries, 1/min, 5/hour) · exchange it for a session |
| `POST` | `/api/auth/google` | Sign in or sign up with a Google ID token |
| `*` | `/api/auth/*`, `/api/keys`, `/api/endpoints` | Password accounts, auth config, and bring-your-own LLM credentials (Fernet-encrypted) |

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
| `LOG_LEVEL` | `INFO` | Fallbacks log at `WARNING` |

## Project layout

```
services/api/app/
  main.py            routes, middleware (CORS, rate limit, body limit, security headers)
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
  routers/           auth · keys (BYOK) · study (user study)
apps/web/
  components/workspace/   one panel per feature + shared UI
  components/markdown.tsx citation-aware Markdown renderer
  components/code-viewer.tsx  drawer that opens cited lines
  components/study.tsx    user-study recorder
evals/               golden questions, eval runner, results, study protocol
```

## Tests

`make test` runs 34 backend tests: citation verification, import graph, living-docs staleness, LLM fallback chain, ingest safety, repo ownership, quotas, migrations, email codes, Google sign-in, tour call-following, production config checks, study API. They run offline and never call a paid model. `make eval` runs the live grounding eval. CI also builds the web app.

## Tools, models and credits

- **AI used to build this:** Claude Code (Anthropic, Claude Opus) helped write and review code. At runtime, Sherpa uses Kimi K2.5 / Qwen3-Coder / DeepSeek V3.2 via AWS Bedrock Mantle, and Amazon Nova multimodal embeddings via Amazon Bedrock.
- **Open-source libraries:** FastAPI, Pydantic, SQLAlchemy, Alembic, pgvector, scikit-learn (TF-IDF), OpenAI Python SDK, PyJWT, passlib, cryptography, httpx; Next.js, React, Tailwind CSS, Framer Motion, lucide-react, sonner, react-markdown, remark-gfm, Mermaid.
- **Demo repository:** [fastapi/full-stack-fastapi-template](https://github.com/fastapi/full-stack-fastapi-template) (MIT).
- Only public code and pseudonymous study data are used. No API keys are committed.

## License

MIT, see [`LICENSE`](LICENSE).
