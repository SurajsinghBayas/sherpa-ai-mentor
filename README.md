# Sherpa — AI Codebase Mentor 🏔️

> An agentic onboarding mentor that reads any code repository and helps newcomers understand it fast — with **every answer grounded in actual code (file:line citations)**.

Built for **IM-05 Codebase Mentor: AI Onboarding for Developers**. Production-grade quality inspired by Dots, Muse, and agentic coding assistants — but purpose-built for onboarding.

![Stage](https://img.shields.io/badge/stage-2%20prototype-blue) ![License](https://img.shields.io/badge/license-MIT-green) ![CI](https://github.com/SurajsinghBayas/sherpa-ai-mentor/actions/workflows/ci.yml/badge.svg)

## What it does

| IM-05 requirement | Where it lives |
|---|---|
| Architecture overview: main parts + how they connect | `POST /api/overview` → `agents/mentor.py::build_overview` + web `ArchGraph` |
| Guided tours of key flows (e.g. "what happens on signup?") | `POST /api/tours` → `build_tour()` + web `TourPlayer` |
| How/why Q&A linked to exact files + lines | `POST /api/ask` → `answer_question()` with citation verifier |
| Suggested starter tasks for first contribution | `POST /api/tasks` → `suggest_starter_tasks()` + web `TaskBoard` |
| Docs that stay fresh as code changes (optional) | `POST /api/freshness` → `check_freshness()` + `make refresh-docs` |

**Grounding guarantee:** every claim the agent makes must resolve to a `file:line-range` that exists in the indexed snapshot. The `CitationVerifier` rejects or flags anything else. No silent hallucinations.

## Agentic character (like Dots / Muse)

Sherpa is not a thin RAG wrapper. It runs a tool loop:

```
planner → search_code → read_file → get_graph → synthesize → verify_citations → answer
```

- **Persona:** `packages/core/prompts/system.md` — encouraging senior-mentor tone, always cites, admits uncertainty.
- **Tools:** `search_code` (FTS + vector, pgvector-ready), `read_file` (exact lines), `get_graph` (imports/call edges).
- **Memory:** per-repo conversation + indexed snapshot id, so follow-ups stay grounded.
- **Providers (BYOK):** OpenAI, Anthropic, Gemini, Ollama — via a tiny `LLMClient` interface. **No key?** Offline extractive fallback still demos fully (templates + retrieval), so judges can run with zero setup.

## Quickstart (2 min, no API key)

```bash
# 1. backend
cd services/api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 2. index a real repo (default demo: a small sample; or point at any local path / GitHub URL)
curl -X POST localhost:8000/api/ingest -H 'Content-Type: application/json' \
  -d '{"repo_url": "https://github.com/gothinkster/realworld", "branch": "main"}'
# → {"repo_id":"...","files":123,"chunks":842}

# 3. ask (grounded)
curl -X POST localhost:8000/api/ask -H 'Content-Type: application/json' \
  -d '{"repo_id":"<id>","question":"How does user signup work?"}'

# 4. frontend
cd apps/web && npm install && npm run dev
# open http://localhost:3000
```

With an LLM key for richer answers:

```bash
export LLM_PROVIDER=openai LLM_MODEL=gpt-4o-mini OPENAI_API_KEY=sk-...
# or: export LLM_PROVIDER=ollama LLM_MODEL=codellama
uvicorn app.main:app --reload
```

Docker:

```bash
docker compose up --build
# api → :8000, web → :3000
```

## SaaS: auth, database, your own keys

Industry-grade multi-user layer (v0.3):

- **JWT auth** — `POST /api/auth/register`, `POST /api/auth/login` → Bearer token, `GET /api/auth/me`. Bcrypt hashes, 24h expiry.
- **Neon Postgres** — set `DATABASE_URL=postgresql+psycopg://…@….neon.tech/sherpa?sslmode=require` (see `docs/neon_setup.md`). Blank = local SQLite, zero setup. `docker compose` also ships a local Postgres.
- **Bring your own keys** — Settings → Keys & Endpoints: add **OpenAI / Anthropic / Gemini / OpenRouter** keys (prefix-validated, Fernet-encrypted, UI shows last4 only) or **any endpoint** (OpenAI-compatible gateway, LiteLLM, Cloudflare AI Gateway, Ollama) with a **Test connection** probe before saving. Pick one per answer in the Mentor.
- **Credential-scoped Q&A** — `POST /api/ask {key_id | endpoint_id}` resolves only the caller's own credentials (403/404 otherwise, covered in `tests/test_auth.py`).
- **Web enrichment (Firecrawl)** — ingest scrapes the GitHub repo page + your docs URLs into `web/…` chunks cited like code. Keyless = code-only, evergreen. See `docs/firecrawl_setup.md`.
- **UI/UX system** — shadcn-style primitives + [Geist](https://fonts.google.com/specimen/Geist) / [Geist Mono](https://fonts.google.com/specimen/Geist+Mono), lucide icons, Sonner toasts, ease-out motion. Rules in `docs/ui_ux_system.md` (distilled from [ui-skills](https://github.com/ibelick/ui-skills) + [emilkowalski/skills](https://github.com/emilkowalski/skills)).

```bash
export JWT_SECRET_KEY="$(openssl rand -hex 32)"
export ENCRYPTION_KEY="$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
# + DATABASE_URL for Neon, then start the API as usual
```

## Repo layout

```
sherpa-ai-mentor/
  services/api/        # FastAPI: ingest, chunk, store, retrieval, agents, routers
    app/
      config.py        # env + provider config
      models.py        # pydantic schemas (AskRequest, Citation, TourStep...)
      chunk.py         # AST-aware chunking (py/js/ts/go fallback-safe)
      store.py         # SQLite FTS + vector (numpy cosine), pgvector-ready interface
      ingest.py        # clone/walk, ignore rules, language detect
      retrieval.py     # hybrid search + MMR
      agents/mentor.py # overview, tour, qa, tasks, freshness + citation verifier
      main.py          # routes: /ingest /ask /overview /tours /tasks /freshness /health
    tests/             # grounding + chunk tests (must pass in CI)
  apps/web/            # Next.js: chat with citations, arch graph, tour player, task board
  packages/core/prompts/system.md  # Sherpa persona
  evals/               # golden Q&A + 5-person user-study protocol for Stage 3
  docs/                # architecture, demo script, Stage-1 pitch
```

## API

- `POST /api/ingest {repo_url|local_path, branch}` → `{repo_id, files, chunks}`
- `POST /api/ask {repo_id, question, history?}` → `{answer_markdown, citations[{file,start_line,end_line,snippet}], confidence, verify:{grounded, ungrouded_claims}}`
- `POST /api/overview {repo_id}` → `{components[{name,path,role}], edges[{from,to,via}], mermaid, summary}`
- `POST /api/tours {repo_id, flow}` → `{title, steps[{caption, file, start_line, end_line, code}], estimated_minutes}`
- `POST /api/tasks {repo_id, level}` → `{tasks[{title, why, files, steps, difficulty}]}`
- `POST /api/freshness {repo_id, docs_markdown}` → `{stale_sections[{heading, reason, suggested_update}]}`
- `GET /health` `GET /api/repos`

## How grounding works

1. Chunk files with `file:start-end` provenance preserved.
2. Retrieve top-k with hybrid FTS+vector + MMR diversity.
3. LLM (or offline template) drafts answer **with required `[file:L1-L2]` markers**.
4. `CitationVerifier` parses markers, checks each exists in snapshot, drops/flags failures, attaches snippets.
5. API returns only verified citations. UI renders each as a clickable chip that opens the exact lines.

## Evals + user test (Stage 3)

- `evals/golden_qa.json` — 12 grounded Q&A pairs; `make eval` checks citation precision.
- `evals/user_study.md` — 5-newcomer protocol (with/without Sherpa, time-to-first-PR). Record results in `docs/user_study_results.md`.

## Roadmap

- [x] Stage 1: pitch (`docs/stage1_pitch.md`)
- [x] Stage 2: Q&A + overview for one repo (this build)
- [ ] Stage 3: tours, starter tasks, freshness watcher, user test
- [ ] pgvector + tree-sitter + GitHub App auto-refresh on push

## Contributing

See `CONTRIBUTING.md`. PRs welcome — good first issues are generated by Sherpa itself (`POST /api/tasks`).

## License

MIT — see `LICENSE`.
