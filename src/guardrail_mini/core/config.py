"""Validated settings loaded from environment variables or a local .env file."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the API process."""

    app_name: str = "Guardrail Mini"
    environment: str = "development"
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    toxicity_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    toxicity_review_threshold: float | None = Field(default=0.55, ge=0.0, le=1.0)
    toxicity_model_dir: Path = Path("models/toxicity/v1")
    model_device: str = "auto"

    @model_validator(mode="after")
    def validate_toxicity_thresholds(self) -> "Settings":
        if (
            self.toxicity_review_threshold is not None
            and self.toxicity_review_threshold > self.toxicity_threshold
        ):
            raise ValueError("The review threshold must not exceed the block threshold.")
        return self

    model_config = SettingsConfigDict(
        env_prefix="GUARDRAIL_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return one validated settings instance per process."""

    return Settings()
