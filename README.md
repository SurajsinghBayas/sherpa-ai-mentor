<div align="center">

<br />

<!-- Sherpa logotype -->
<img src="https://img.shields.io/badge/Sherpa-AI%20Codebase%20Mentor-0a0a0a?style=for-the-badge&labelColor=0a0a0a&color=4a9eff" alt="Sherpa" />

<br /><br />

**Understand any codebase, immediately.**

Sherpa is an agentic AI guide that reads any GitHub repository and answers your questions with verified, file:line grounded citations. No hallucinations. No guessing.

<br />

[![CI](https://github.com/SurajsinghBayas/sherpa-ai-mentor/actions/workflows/ci.yml/badge.svg)](https://github.com/SurajsinghBayas/sherpa-ai-mentor/actions/workflows/ci.yml)
![License](https://img.shields.io/badge/license-MIT-22c55e?style=flat)
![Next.js](https://img.shields.io/badge/Next.js-14-black?style=flat&logo=next.js)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat&logo=fastapi)
![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python)

<br />

</div>

---

## What is Sherpa?

Sherpa is your AI guide through any codebase. Like having a senior engineer on-call, except Sherpa has read every file, remembers every import, and never gets tired of questions.

Every answer is grounded in the actual code snapshot. Sherpa parses every `[file:L1-L2]` citation it generates, checks it exists in the repo, and drops anything it can't verify. Zero hallucinations by design.

```
You  → "How does user authentication work?"

Sherpa → "Auth flows through POST /api/auth/login. The handler validates
          credentials with bcrypt, then issues a 24h JWT signed with your
          configured secret.

          Sources:
          · app/routers/auth.py:38-44
          · app/security.py:22-33"
```

---

## Features

| Feature | Description |
|---|---|
| **Grounded Q&A** | Every answer cites `file:line`. The `CitationVerifier` drops unverifiable claims before they reach the UI. |
| **Architecture maps** | Components, roles, and import edges rendered as a live Mermaid graph. |
| **Guided tours** | Trace any flow (signup, checkout, upload…) step-by-step with code inline at each stop. |
| **Starter tasks** | First-PR-sized tasks generated from the actual repo, with files and steps attached. |
| **Zero-config LLM** | Powered by DeepSeek V3 via Bedrock Mantle — no API key required for any user. |
| **BYOK** | Power users can add OpenAI / Anthropic / Gemini / custom endpoints. Encrypted at rest. |
| **JWT + Postgres** | Real multi-user auth, Neon Postgres in prod, SQLite zero-setup fallback. |

---

## Architecture

```
┌─────────────────────┐
│   Next.js 14 UI     │  Sherpa orb · chat · citations · arch graph · tour · tasks
└────────┬────────────┘
         │ REST / JSON
┌────────▼────────────┐
│   FastAPI (Python)  │  /ingest /ask /overview /tours /tasks /freshness /health
└──┬────────┬─────────┘
   │        │
   ▼        ▼
ingest   retrieval          agents/mentor.py
clone/   hybrid FTS         planner → search_code → read_file
walk +   + vector           → synthesize → CitationVerifier
chunk    MMR diversity       → verified answer + citations
   │        │
   └────────┴─────────────┐
                           ▼
                     RepoStore
                  chunks.json + TF-IDF
                  (pgvector-ready interface)
```

**Key design choices:**

- **Provenance-first chunking** — every chunk carries `file:start_line-end_line`. AST-aware for Python, safe generic splitter for everything else.
- **Swappable retrieval** — today: SQLite + TF-IDF (zero infra, works offline). Interface matches pgvector for scale.
- **CitationVerifier** — parses `[file:L1-L2]` markers, checks existence in snapshot, drops ghosts. This is the grounding guarantee.
- **One-retry self-correction** — if the LLM forgets citations, Sherpa sends a targeted correction prompt and takes the better answer.
- **SSRF guard** — `/api/ingest` only allows `github.com`, `gitlab.com`, `bitbucket.org`.

---

## Quickstart

### Backend

```bash
cd services/api

# create env (copy example and fill in values)
cp ../../.env.example .env

# install
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# start
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd apps/web
npm install
npm run dev
# → http://localhost:3000
```

### Docker (full stack)

```bash
docker compose up --build
# api → :8000, web → :3000
```

---

## API Reference

All endpoints accept and return JSON.

### Ingest

```http
POST /api/ingest
Content-Type: application/json

{
  "repo_url": "https://github.com/gothinkster/realworld",
  "branch": "main",
  "docs_urls": ["https://docs.example.com"],
  "enrich_web": true
}
```

```json
{ "repo_id": "abc123", "files": 87, "chunks": 1243, "web_sources": [] }
```

### Ask

```http
POST /api/ask
Authorization: Bearer <token>
Content-Type: application/json

{
  "repo_id": "abc123",
  "question": "How does user signup work?"
}
```

```json
{
  "answer_markdown": "User signup flows through POST /api/auth/register...",
  "citations": [
    { "file": "app/routers/auth.py", "start_line": 22, "end_line": 34, "snippet": "..." }
  ],
  "confidence": 0.85,
  "verify": { "grounded": true, "unchecked_claims": [] }
}
```

### Overview

```http
POST /api/overview
{ "repo_id": "abc123" }
```

```json
{
  "summary": "...",
  "mermaid": "graph TD\n  app --> routers\n  routers --> models",
  "components": [{ "name": "routers · route/handler", "path": "routers", "role": "route/handler" }],
  "edges": [{ "from": "routers", "to": "models", "via": "imports" }]
}
```

### Tours · Tasks · Freshness

```http
POST /api/tours   { "repo_id": "...", "flow": "user signup" }
POST /api/tasks   { "repo_id": "...", "level": "beginner" }
POST /api/freshness { "repo_id": "...", "docs_markdown": "..." }
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `JWT_SECRET_KEY` | ✅ | Long random string for JWT signing |
| `DATABASE_URL` | Prod only | Neon Postgres connection string |
| `ENCRYPTION_KEY` | Prod only | Fernet key for encrypting stored API keys |
| `OPENAI_API_KEY` | — | Server-side LLM key (Bedrock Mantle pre-configured) |
| `OPENAI_BASE_URL` | — | LLM base URL (default: Bedrock Mantle) |
| `LLM_MODEL` | — | Model name (default: `deepseek.v3.2`) |
| `FIRECRAWL_API_KEY` | — | Optional — enables web doc scraping |
| `ALLOWED_ORIGINS` | Prod | Comma-separated CORS origins |

Generate production secrets:

```bash
export JWT_SECRET_KEY="$(openssl rand -hex 32)"
export ENCRYPTION_KEY="$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
```

---

## Project Layout

```
sherpa-ai-mentor/
├── apps/
│   ├── web/                    # Next.js 14 frontend
│   │   ├── app/
│   │   │   ├── page.tsx        # Landing page
│   │   │   ├── dashboard/      # Main app
│   │   │   ├── login/          # Auth
│   │   │   └── signup/
│   │   └── components/
│   │       ├── sherpa-orb.tsx  # Animated Sherpa character
│   │       ├── dashboard.tsx   # Chat UI + panels
│   │       ├── site-header.tsx
│   │       └── ui/primitives.tsx
│   └── ad/                     # Remotion product video
│       └── src/SherpaAd.tsx    # 30-second ad, 5 scenes
├── services/
│   └── api/                    # FastAPI backend
│       └── app/
│           ├── main.py         # Routes + security middleware
│           ├── config.py       # Settings (pydantic-settings)
│           ├── chunk.py        # AST-aware code chunker
│           ├── store.py        # RepoStore: FTS + vector
│           ├── ingest.py       # Clone/walk/chunk pipeline
│           ├── retrieval.py    # Hybrid search + MMR
│           ├── agents/
│           │   └── mentor.py   # LLMClient + all agent flows
│           └── routers/
│               ├── auth.py     # Register / login / me
│               └── keys.py     # BYOK key management
├── packages/
│   └── core/prompts/
│       └── system.md           # Sherpa persona prompt
├── evals/
│   └── golden_qa.json          # 12 grounded Q&A pairs for CI
├── docs/                       # Architecture, pitch, setup guides
└── docker-compose.yml
```

---

## Security

- **CORS** — locked to `ALLOWED_ORIGINS` env var (defaults to `localhost:3000` only)
- **Rate limiting** — 60 req/min per IP per endpoint (configurable via `RATE_LIMIT_PER_MINUTE`)
- **Security headers** — `X-Content-Type-Options`, `X-Frame-Options`, `HSTS`, `Referrer-Policy`, `Permissions-Policy`
- **Body size limit** — 1 MB max, configurable via `MAX_BODY_BYTES`
- **SSRF guard** — `/api/ingest` only allows `github.com`, `gitlab.com`, `bitbucket.org`
- **JWT auth** — bcrypt hashed passwords, 24h token expiry, Bearer scheme
- **Credential encryption** — Fernet encryption on all stored API keys; UI shows last 4 chars only

---

## Development

```bash
# Run tests
cd services/api
pytest tests/ -v

# Lint
ruff check app/

# Type-check frontend
cd apps/web
npm run build

# Render the ad video
cd apps/ad
npm install
npm run render
# → out/sherpa-ad.mp4
```

---

## Roadmap

- [x] Stage 1 — pitch and architecture design
- [x] Stage 2 — grounded Q&A + architecture overview
- [x] Stage 3 — tours, starter tasks, freshness watcher, BYOK, auth
- [x] Production UI — animated Sherpa agent, dark design system, chat interface
- [x] Zero-config LLM — Bedrock Mantle, no user API keys required
- [ ] pgvector — swap TF-IDF for hosted embeddings, no code changes needed
- [ ] Tree-sitter — richer AST chunking for TypeScript, Go, Rust
- [ ] GitHub App — webhook auto-reindex on push, `check_freshness` opens PRs
- [ ] Streaming — SSE responses for long answers

---

## Contributing

Good first issues are generated by Sherpa itself — run `POST /api/tasks` against this repo. See [`CONTRIBUTING.md`](CONTRIBUTING.md).

---

## License

MIT — see [`LICENSE`](LICENSE).

---

<div align="center">
  <sub>Built with care. Every answer is grounded.</sub>
</div>
