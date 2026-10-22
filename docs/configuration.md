# Configuration

All settings are environment variables (or a `.env` file in the repo root); [`.env.example`](../.env.example) lists them with comments. For a production server, see [`deployment_guide.md`](deployment_guide.md).

| Variable | Default | Notes |
|---|---|---|
| `ENVIRONMENT` | `development` | `production` enables the startup safety checks |
| `LLM_PROVIDER` | `none` | `openai` (any OpenAI-compatible gateway) · `openrouter` · `anthropic` · `gemini` · `ollama` |
| `LLM_MODEL` | `qwen.qwen3-coder-480b-a35b-instruct` when provider is `openai` | |
| `LLM_FALLBACK_MODELS` | `qwen.qwen3-coder-480b-a35b-instruct,deepseek.v3.2` | Tried in order; each fallback is logged |
| `OPENAI_API_KEY` / `OPENAI_BASE_URL` | — | e.g. `https://bedrock-mantle.ap-south-1.api.aws/v1` |
| `JWT_SECRET_KEY` | dev value | Set a long random value in production |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `MAIL_FROM_NAME` | — / 587 / — / — / `Sherpa AI` | Email sign-in codes (Gmail app password works) |
| `GOOGLE_CLIENT_ID` | — | Google sign-in (OAuth client, Web application); button hidden when blank |
| `DATABASE_URL` | SQLite | AWS RDS Postgres in production (see `docs/rds_setup.md`); holds accounts, repos, chunks and embeddings |
| `AWS_BEARER_TOKEN_BEDROCK` | — | Bedrock API key for embeddings; blank → TF-IDF search |
| `EMBEDDING_MODEL` / `EMBEDDING_REGION` | `amazon.titan-embed-text-v2:0` / `ap-south-1` | Titan v2 runs next to RDS and the LLM. `amazon.nova-2-multimodal-embeddings-v1:0` works too but only in `us-east-1`. After changing the model, run `make reembed` |
| `AWS_DEFAULT_REGION` | `us-east-1` | Polly's region when `POLLY_REGION` is blank, and embeddings' when `EMBEDDING_REGION` is blank |
| `DAILY_LLM_REQUESTS` / `DAILY_INGESTS` / `MAX_REPOS_PER_USER` | 300 / 30 / 15 | Per-user quotas |
| `ENCRYPTION_KEY` | derived | Fernet key for stored user API keys |
| `ALLOW_LOCAL_INGEST` | `false` | Lets the API read server folders; local dev only |
| `ALLOWED_ORIGINS` | `http://localhost:3000` | CORS |
| `RATE_LIMIT_PER_MINUTE` / `MAX_BODY_BYTES` | 60 / 1 MB | Per user per endpoint · request size |
| `MAX_CONCURRENT_INGESTS` / `MAX_REPO_MB` / `CLONE_TIMEOUT_SECONDS` | 3 / 500 / 180 | Ingest limits |
| `LLM_TIMEOUT_SECONDS` | 90 | Per model call |
| `MAX_UPLOAD_MB` / `MAX_UPLOAD_SOURCE_MB` | 100 / 50 | Uploaded ZIP size · text kept after filtering |
| `LOG_LEVEL` | `INFO` | Fallbacks log at `WARNING` |
| `PRIVATE_TTL_HOURS` / `MAX_PRIVATE_REPOS` | 8 / 20 | Private mode: how long code stays in memory · how many private repos one server holds |
| `POLLY_ACCESS_KEY_ID` / `POLLY_SECRET_ACCESS_KEY` / `POLLY_REGION` | — / — / `us-east-1` | Amazon Polly voice; blank → the browser's built-in voice |
| `POLLY_VOICE` / `POLLY_ENGINE` | `Matthew` / `neural` | |
