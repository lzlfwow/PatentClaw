from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PR_", env_file=".env", extra="ignore")

    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-5.5"
    openai_user_agent: str | None = "Mozilla/5.0"
    enable_semantic_review: bool = False
    output_root: Path = Field(default=Path("data"))
    max_source_chars: int = 120_000


def get_settings() -> Settings:
    return Settings()

