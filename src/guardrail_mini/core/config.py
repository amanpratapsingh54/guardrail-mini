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
    database_url: str | None = None
    toxicity_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    toxicity_review_threshold: float | None = Field(default=0.55, ge=0.0, le=1.0)
    toxicity_model_dir: Path = Path("models/toxicity/v1")
    pii_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    pii_review_threshold: float | None = Field(default=0.55, ge=0.0, le=1.0)
    prompt_injection_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    prompt_injection_review_threshold: float | None = Field(default=0.55, ge=0.0, le=1.0)
    prompt_injection_model_dir: Path = Path("models/prompt-injection/v1")
    model_device: str = "auto"

    @model_validator(mode="after")
    def validate_review_thresholds(self) -> "Settings":
        for policy_id in ("toxicity", "pii", "prompt_injection"):
            block_threshold = getattr(self, f"{policy_id}_threshold")
            review_threshold = getattr(self, f"{policy_id}_review_threshold")
            if review_threshold is not None and review_threshold > block_threshold:
                raise ValueError(
                    f"The {policy_id} review threshold must not exceed its block threshold."
                )
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
