# Architecture

```
                 ┌──────────────────────────────────────────────┐
                 │ Next.js UI                                    │
                 │ Architecture · Ask · Tours · Tasks · Docs ·   │
                 │ User study   — citation chips → code drawer   │
                 └───────────────────────┬──────────────────────┘
                                         │ REST (JWT)
                 ┌───────────────────────▼──────────────────────┐
                 │ FastAPI  main.py + routers (auth, keys, study)│
                 └──┬───────────────┬───────────────┬───────────┘
                    │               │               │
            ┌───────▼──────┐ ┌──────▼──────┐ ┌──────▼───────────────┐
            │ ingest.py    │ │ analysis.py │ │ agents/               │
            │ clone/walk,  │ │ import graph│ │ mentor   (Q&A)        │
            │ skip secrets │ │ components  │ │ overview (map)        │
            │ chunk.py     │ │ entrypoints │ │ tour     (flows)      │
            └───────┬──────┘ │ task signals│ │ tasks    (first PRs)  │
                    │        └──────┬──────┘ │ docs     (living docs)│
            ┌───────▼───────────────▼──┐     │ common   (VERIFIER)   │
            │ RepoStore  store.py      │◀────┤                       │
            │ chunks + full files +    │     └──────────┬────────────┘
            │ hashes · keyword search  │                │
            │ persist.py → Postgres +  │         ┌──────▼──────┐
            │ pgvector (Nova embeds)   │         │             │
            └──────────────────────────┘         │ llm.py      │ default model → fallbacks
                                                 │             │ → offline composer (logged)
                                                 └─────────────┘
```

## Data flow

1. **Ingest** (`POST /api/ingest`): shallow-clone or walk the repo. Skip junk dirs, `.env*` secrets, keys, databases, lockfiles and binaries. Chunk with provenance and save the snapshot to the database (`repos`, `repo_files`, `repo_chunks`) under an id scoped to the user. Embed any chunk whose content hash has no vector yet. Re-ingesting diffs per-file hashes and clears derived caches.
2. **Analysis** (`analysis.py`, cached per snapshot): resolve Python and JS/TS imports into a file graph, group files into ~10 components (breadth-first, tests and docs set aside), and find entrypoints and task signals.
3. **Ask**: alias expansion → hybrid retrieval → one hop along the import graph → LLM with `--- path:start-end ---` headers → verifier → answer. One retry if no citation survives; otherwise the offline composer.
4. **Overview**: static components and edges + LLM descriptions (JSON) → Mermaid with layer subgraphs and import counts.
5. **Tour**: route-biased retrieval + import expansion produce numbered candidates. The LLM picks and orders them, so every step is real code.
6. **Tasks**: static signals (TODO, untested module, long function, missing docs) → LLM picks five diverse ones → file refs validated.
7. **Living docs**: five sections, each storing the hashes of the files it cites. `POST /api/sync` re-ingests, marks only sections whose files changed, regenerates those, and records a changelog.

## Design decisions

- **The verifier is the product.** `agents/common.py` parses `[file:L1-L2]`, resolves short paths, splits combined ranges, checks the lines exist, and removes the rest from the text.
- **Candidates, not free text.** Tours and tasks make the model choose from numbered snippets, so they cannot cite invented code.
- **Degrade, don't die.** `llm.py` walks `LLM_FALLBACK_MODELS` and then falls back to an extractive answer. Every step logs a warning, and the UI labels offline output.
- **BYOK is isolated.** User keys never use the server fallback chain. The OpenAI client pins `base_url` and project so env vars for the default gateway don't leak into user calls.
- **Postgres is the system of record.** Users, repos, files, chunks, cached agent output and embeddings all live in AWS RDS Postgres, so API containers are stateless and can be redeployed or scaled freely. Locally, SQLite + TF-IDF still works with zero setup.
- **Embeddings are content-addressed.** `chunk_embeddings` is keyed by (model, sha1 of path + text). Re-indexing, syncing and other users indexing the same repo reuse vectors, so only changed code costs a Bedrock call.
- **Owned and metered.** Every repo has an owner; other users get 404. LLM and ingest calls count against daily per-user quotas.

## Scaling notes

- Search scans one repo's vectors exactly (filtered by `repo_id`). Past ~50k chunks per repo, add an HNSW index in a migration.
- Indexing runs inside the request (~40 s for a 700-chunk repo on first index). Move it to a background job for very large repos.
- Add tree-sitter chunking for Go/Java; `chunk_file` already dispatches by extension.
- A GitHub webhook calling `/api/sync` on push would keep living docs current automatically.
