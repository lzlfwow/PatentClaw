from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings. Credentials are server-side only."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    offline_mode: bool = Field(default=True, alias="L2D_OFFLINE_MODE")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: str | None = Field(default=None, alias="OPENAI_BASE_URL")
    openai_user_agent: str | None = Field(default=None, alias="L2D_OPENAI_USER_AGENT")
    openai_max_retries: int = Field(default=6, alias="L2D_OPENAI_MAX_RETRIES")
    openai_timeout_seconds: float = Field(default=180.0, alias="L2D_OPENAI_TIMEOUT_SECONDS")
    model: str = Field(default="gpt-5.4-mini", alias="L2D_MODEL")
    review_model: str = Field(default="gpt-5.4", alias="L2D_REVIEW_MODEL")
    enable_review: bool = Field(default=True, alias="L2D_ENABLE_REVIEW")
    data_dir: Path = Field(default=Path("data"), alias="L2D_DATA_DIR")
    max_upload_mb: int = Field(default=50, alias="L2D_MAX_UPLOAD_MB")
    max_expanded_mb: int = Field(default=150, alias="L2D_MAX_EXPANDED_MB")
    max_latex_chars: int = Field(default=300_000, alias="L2D_MAX_LATEX_CHARS")

    def prepare(self) -> "Settings":
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "jobs").mkdir(parents=True, exist_ok=True)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings().prepare()
