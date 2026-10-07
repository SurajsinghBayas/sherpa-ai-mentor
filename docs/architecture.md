# Architecture

```
              ┌─────────────┐
              │  Next.js UI │  chat + citations, arch graph, tour player, task board
              └──────┬──────┘
                     │ REST
              ┌──────▼──────┐
              │ FastAPI api │  /ingest /ask /overview /tours /tasks /freshness
              └──────┬──────┘
        ┌────────────┼────────────┐
        │            │            │
   ┌────▼───┐  ┌─────▼────┐ ┌─────▼─────┐
   │ ingest │  │ retrieval│ │  agents   │
   │ clone/ │  │ hybrid   │ │ mentor.py │
   │ walk + │  │ FTS+vec  │ │ overview/ │
   │ chunk  │  │ MMR      │ │ tour/qa/  │
   └────┬───┘  └─────┬────┘ │ tasks/    │
        │            │      │ freshness │
        └────────────┼──────┘     │
                     │      ┌─────▼────────┐
              ┌──────▼──────▼──┐ verifier  │
              │ RepoStore      │▲ citations│
              │ SQLite files + │ must exist│
              │ TF-IDF (pgvec │ in snapshot
              │ ready)         │
              └────────────────┘
```

## Why this shape (production-grade)

- **Provenance-first chunking** (`chunk.py`): AST-aware for Python, safe generic splitter otherwise. Every chunk carries `file:start-end`.
- **Swappable retrieval** (`store.py` + `retrieval.py`): today SQLite + TF-IDF (zero infra, works offline); interface matches pgvector + hosted embeddings for scale. Hybrid keyword+vector + MMR diversity.
- **Agentic mentor** (`agents/mentor.py`): planner → tools → synthesize → **CitationVerifier**. The verifier is the product: it parses `[file:L1-L2]`, checks existence in the snapshot, and drops ghosts.
- **BYOK LLM** (`LLMClient`): OpenAI / Anthropic / Gemini / Ollama; offline extractive fallback so Stage-2 demo never needs a key.
- **Typed contract** (`models.py`): Pydantic schemas shared by API + web UI.
- **Evals** (`tests/test_grounding.py`, `evals/`): citation precision is tested in CI.

## Data flow

1. `POST /api/ingest` clones (shallow) or walks, ignores junk dirs, chunks, saves `data/<repo_id>/`.
2. `POST /api/ask` expands aliases ("sign up" → signup/register/auth...), retrieves top-k, composes (LLM or offline), verifies citations, returns.
3. `POST /api/overview` groups by top-dir + role, scans imports for edges, emits mermaid.
4. `POST /api/tours` keyword-plans the flow, orders route→logic→model, returns steps with code.
5. `POST /api/freshness` diffs docs headings/paths against the snapshot.

## Scaling notes

- Replace `TfidfVectorizer` with `pgvector` + `text-embedding-3-small`; no agent changes.
- Add tree-sitter for TS/Go chunking; `chunk_file` already dispatches by extension.
- GitHub App webhook → re-ingest on push → `check_freshness` opens doc-update PRs.
