"""Central config — env-driven, 12-factor. No secrets in code."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    app_name: str = "sherpa-ai-mentor"
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


settings = Settings()
