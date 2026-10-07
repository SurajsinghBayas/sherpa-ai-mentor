"""Central config — env-driven, 12-factor. No secrets in code.

SaaS additions: JWT auth, DATABASE_URL (Neon Postgres in prod,
SQLite fallback for zero-setup local dev), and a Fernet key used to
encrypt users' stored LLM provider keys at rest.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    app_name: str = "sherpa-ai-mentor"

    # retrieval / chunking
    data_dir: str = "./data"
    llm_provider: str = "none"  # none | openai | anthropic | gemini | ollama
    llm_model: str = "offline"
    openai_api_key: str = ""
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

    # database — Neon Postgres in prod, e.g.
    # postgresql+psycopg://user:pass@ep-xxx.neon.tech/sherpa?sslmode=require
    # Empty/blank falls back to local SQLite so `make api` works with zero setup.
    database_url: str = ""
    encryption_key: str = ""  # Fernet key; generated from jwt_secret_key if blank


settings = Settings()
