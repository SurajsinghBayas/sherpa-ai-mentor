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

    # Rate limiting — requests per minute per IP per endpoint
    rate_limit_per_minute: int = 60

    # Request body size limit in bytes (default 1 MB)
    max_body_bytes: int = 1 * 1024 * 1024


settings = Settings()


def production_problems(s: Settings) -> list[str]:
    """Settings that are fine on a laptop but unsafe on a public server."""
    if s.environment.lower() != "production":
        return []
    out = []
    if s.jwt_secret_key == "dev-only-change-me" or len(s.jwt_secret_key) < 32:
        out.append("JWT_SECRET_KEY must be a random value of at least 32 characters")
    if not s.encryption_key:
        out.append("ENCRYPTION_KEY must be set (Fernet key)")
    if not s.database_url:
        out.append("DATABASE_URL must point at Postgres (local SQLite is lost on redeploy)")
    if s.allow_local_ingest:
        out.append("ALLOW_LOCAL_INGEST must be false")
    if "*" in s.allowed_origins:
        out.append("ALLOWED_ORIGINS must list real origins, not *")
    return out
