# How Sherpa works

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
