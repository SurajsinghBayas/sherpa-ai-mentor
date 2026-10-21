# Security and privacy

## Private mode

For code that must not be stored: the repository's files, chunks, embedding vectors and generated outputs (overview, tours, docs) are held in the API process's memory only and never written to the database or disk. The database keeps one summary row (name, URL, counts, expiry). Everything is wiped when the user deletes the repo, after `PRIVATE_TTL_HOURS` (default 8), or when the API restarts. Private GitHub, GitLab and Bitbucket repositories are cloned with a one-time read-only token, passed to git as an auth header through its environment (not the command line, the URL or `.git/config`), with redirects refused; it is never stored or logged. Model calls go to Amazon Bedrock, which doesn't store or train on prompts. Private mode assumes a single API instance (or sticky sessions).

## What is never indexed

Ingest skips `.env*` files (templates like `.env.example` are kept), databases, private keys, lockfiles, binaries and media. Uploads are filtered in the browser or CLI first, so `node_modules`, `.git`, build output and secrets never leave the machine.

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
