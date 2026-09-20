"""Validated settings loaded from environment variables or a local .env file."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the API process."""

    app_name: str = "Guardrail Mini"
    environment: str = "development"
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    database_url: str | None = None
    max_request_body_bytes: int = Field(default=65_536, ge=1_024, le=1_048_576)
    rate_limit_requests_per_minute: int = Field(default=600, ge=1, le=100_000)
    minio_endpoint_url: AnyHttpUrl | None = None
    minio_access_key: str | None = None
    minio_secret_key: SecretStr | None = None
    minio_bucket: str = "guardrail-models"
    artifact_cache_dir: Path = Path("data/model-cache")
    api_key_cache_ttl_seconds: int = Field(default=30, ge=1, le=300)
    demo_enabled: bool = False
    demo_rate_limit_requests_per_minute: int = Field(default=10, ge=1, le=100)
    toxicity_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    toxicity_review_threshold: float | None = Field(default=0.55, ge=0.0, le=1.0)
    toxicity_model_dir: Path = Path("models/toxicity/v1")
    pii_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    pii_review_threshold: float | None = Field(default=0.55, ge=0.0, le=1.0)
    prompt_injection_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    prompt_injection_review_threshold: float | None = Field(default=0.55, ge=0.0, le=1.0)
    prompt_injection_model_dir: Path = Path("models/prompt-injection/v1")
    model_device: str = "auto"
    model_runtime: Literal["pytorch", "onnxruntime"] = "pytorch"
    onnx_cache_dir: Path = Path("data/onnx-cache")

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

    @model_validator(mode="after")
    def validate_artifact_store(self) -> "Settings":
        configured = (
            self.minio_endpoint_url is not None,
            self.minio_access_key is not None,
            self.minio_secret_key is not None,
        )
        if any(configured) and not all(configured):
            raise ValueError("Configure the MinIO endpoint, access key, and secret key together.")
        if self.minio_endpoint_url is not None and self.database_url is None:
            raise ValueError(
                "GUARDRAIL_DATABASE_URL is required when MinIO artifact storage is enabled."
            )
        if not self.minio_bucket or "/" in self.minio_bucket:
            raise ValueError("The MinIO bucket must be a non-empty bucket name without slashes.")
        return self

    @model_validator(mode="after")
    def validate_model_runtime(self) -> "Settings":
        if self.model_runtime == "onnxruntime" and self.model_device not in {"auto", "cpu"}:
            raise ValueError("The ONNX Runtime backend currently supports CPU inference only.")
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
