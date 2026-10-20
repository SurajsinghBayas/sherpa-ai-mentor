"""Central config — env-driven, 12-factor. No secrets in code.

SaaS additions: JWT auth, DATABASE_URL (AWS RDS Postgres in prod,
SQLite fallback for zero-setup local dev), and a Fernet key used to
encrypt users' stored LLM provider keys at rest.
"""
import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def load_local_env() -> None:
    """Load the nearest .env into the process. Existing env vars win."""
    here = Path(__file__).resolve()
    for directory in (here.parent, *here.parents):
        env_file = directory / ".env"
        if not env_file.is_file():
            continue
        for line in env_file.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
        return


load_local_env()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    app_name: str = "sherpa-ai-mentor"

    # retrieval / chunking
    data_dir: str = "./data"
    llm_provider: str = "none"  # none | openai | openrouter | anthropic | gemini | ollama
    llm_model: str = ""          # blank + openai → moonshotai.kimi-k2.5 (see app/llm.py)
    llm_fallback_models: str = ""  # comma-separated; tried in order when the main model fails
    openai_api_key: str = ""
    openai_base_url: str = ""   # e.g. https://bedrock-mantle.us-east-1.api.aws/v1
    openai_project_id: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    max_chunks_per_query: int = 8
    chunk_lines: int = 60
    chunk_overlap: int = 12

    # auth (JWT) — set a long random value in production!
    jwt_secret_key: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 1 day

    # database — AWS RDS Postgres in prod, e.g.
    # postgresql+psycopg://postgres:pass@db.xxxx.ap-south-1.rds.amazonaws.com:5432/postgres?sslmode=require
    # Empty/blank falls back to local SQLite so `make api` works with zero setup.
    database_url: str = ""
    encryption_key: str = ""  # Fernet key; generated from jwt_secret_key if blank

    # embeddings (Amazon Bedrock Nova) — stored in Postgres/pgvector; blank token → TF-IDF only
    aws_bearer_token_bedrock: str = ""
    aws_default_region: str = "us-east-1"
    embedding_model: str = "amazon.nova-2-multimodal-embeddings-v1:0"
    embedding_dim: int = 1024
    embedding_concurrency: int = 16

    # spoken explanations (Amazon Polly). Needs IAM keys with polly:SynthesizeSpeech — the
    # Bedrock API key can't sign Polly calls. Blank keys → boto3's usual chain (env, ~/.aws, role);
    # no credentials → the web app uses the browser's own voice.
    polly_enabled: bool = True
    polly_access_key_id: str = ""
    polly_secret_access_key: str = ""
    polly_region: str = ""          # blank → aws_default_region
    polly_voice: str = "Ruth"
    # neural starts speaking in ~0.5s; generative sounds richer but takes ~2-3s per sentence
    polly_engine: str = "neural"    # neural | generative | standard; generative falls back to neural

    # email one-time codes (Gmail SMTP with an app password)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    mail_from_name: str = "Sherpa AI"
    otp_ttl_seconds: int = 600

    # Google sign-in (OAuth client ID of type "Web application")
    google_client_id: str = ""

    # per-user quotas (reset daily, UTC)
    daily_llm_requests: int = 300
    daily_ingests: int = 30
    max_repos_per_user: int = 15

    # development | production — production refuses to start with unsafe settings
    environment: str = "development"

    # Ingesting a server-side folder (local_path) exposes that folder's files through
    # the API — only enable it on your own machine.
    allow_local_ingest: bool = False

    # CORS — comma-separated allowed origins; "*" allows all (dev only)
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    # The desktop app's own origins (Tauri 2): tauri://localhost on macOS/Linux, http(s)://tauri.localhost
    # on Windows. Browsers can't send these, so they are allowed alongside the https-only web origins.
    desktop_origins: str = "tauri://localhost,http://tauri.localhost,https://tauri.localhost"

    # Rate limiting — requests per minute per user (or IP) per endpoint; auth routes are
    # stricter (see routers/auth.py). Off only for tests.
    rate_limits_enabled: bool = True
    rate_limit_per_minute: int = 60

    # Ingest guardrails: cloning is CPU/disk/network heavy
    max_concurrent_ingests: int = 3       # across the whole instance; extra requests get 503
    max_repo_mb: int = 500                # clone size cap (checked after clone, before indexing)
    clone_timeout_seconds: int = 180

    # Uploaded codebases (ZIP / folder / CLI)
    max_upload_mb: int = 100              # size of the uploaded ZIP
    max_upload_source_mb: int = 50        # text kept after filtering (what gets indexed)

    # LLM guardrails
    llm_timeout_seconds: int = 90         # per model call; fallbacks each get their own

    # Request body size limit in bytes (default 1 MB)
    max_body_bytes: int = 1 * 1024 * 1024


    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() == "production"


settings = Settings()


def production_problems(s: Settings) -> list[str]:
    """Settings that are fine on a laptop but unsafe on a public server."""
    if not s.is_production:
        return []
    out = []
    if s.jwt_secret_key == "dev-only-change-me" or len(s.jwt_secret_key) < 32:
        out.append("JWT_SECRET_KEY must be a random value of at least 32 characters")
    if not s.encryption_key:
        out.append("ENCRYPTION_KEY must be set (Fernet key)")
    else:
        try:
            from cryptography.fernet import Fernet
            Fernet(s.encryption_key.strip().encode())
        except Exception:  # noqa: BLE001 — any parse failure means stored keys can't be read
            out.append("ENCRYPTION_KEY is not a valid Fernet key (Fernet.generate_key())")
        if s.encryption_key.strip() == s.jwt_secret_key.strip():
            out.append("ENCRYPTION_KEY must differ from JWT_SECRET_KEY")
    url = s.database_url.strip()
    if not url or url.startswith("sqlite"):
        out.append("DATABASE_URL must point at Postgres (local SQLite is lost on redeploy)")
    elif "sslmode=disable" in url and not any(h in url for h in ("@localhost", "@127.0.0.1", "@db:", "@db/")):
        out.append("DATABASE_URL must not disable SSL for a remote database")
    if s.allow_local_ingest:
        out.append("ALLOW_LOCAL_INGEST must be false")
    origins = [o.strip() for o in s.allowed_origins.split(",") if o.strip()]
    if not origins or "*" in origins:
        out.append("ALLOWED_ORIGINS must list real origins, not *")
    elif any(not o.startswith("https://") for o in origins):
        out.append("ALLOWED_ORIGINS must all be https:// in production")
    if not s.rate_limits_enabled:
        out.append("RATE_LIMITS_ENABLED must be true")
    return out


def production_warnings(s: Settings) -> list[str]:
    """Not fatal, but a production server should not run like this."""
    if not s.is_production:
        return []
    out = []
    if not (s.smtp_host and s.smtp_user and s.smtp_password) and not s.google_client_id:
        out.append("no SMTP and no GOOGLE_CLIENT_ID: only password sign-in will work")
    if not s.aws_bearer_token_bedrock:
        out.append("AWS_BEARER_TOKEN_BEDROCK unset: search falls back to keyword-only (TF-IDF)")
    return out
