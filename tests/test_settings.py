"""Configuration validation tests."""

import pytest
from pydantic import AnyHttpUrl, SecretStr, TypeAdapter, ValidationError

from guardrail_mini.core.config import Settings


def test_review_threshold_cannot_exceed_block_threshold() -> None:
    with pytest.raises(ValidationError, match="review threshold must not exceed"):
        Settings(  # type: ignore[call-arg]
            _env_file=None, toxicity_threshold=0.6, toxicity_review_threshold=0.7
        )


def test_thresholds_can_be_configured_without_a_review_band() -> None:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None, toxicity_threshold=0.75, toxicity_review_threshold=None
    )
    assert settings.toxicity_threshold == 0.75
    assert settings.toxicity_review_threshold is None


def test_request_security_limits_are_bounded() -> None:
    settings = Settings(
        _env_file=None,
        max_request_body_bytes=131_072,
        rate_limit_requests_per_minute=120,
    )  # type: ignore[call-arg]
    assert settings.max_request_body_bytes == 131_072
    assert settings.rate_limit_requests_per_minute == 120

    with pytest.raises(ValidationError):
        Settings(_env_file=None, max_request_body_bytes=100)  # type: ignore[call-arg]


def test_minio_requires_endpoint_and_both_credentials() -> None:
    with pytest.raises(ValidationError, match="endpoint, access key, and secret key together"):
        Settings(  # type: ignore[call-arg]
            _env_file=None,
            minio_endpoint_url=TypeAdapter(AnyHttpUrl).validate_python("http://127.0.0.1:9000"),
        )


def test_minio_requires_database_for_model_registry_metadata() -> None:
    with pytest.raises(ValidationError, match="DATABASE_URL is required"):
        Settings(  # type: ignore[call-arg]
            _env_file=None,
            minio_endpoint_url=TypeAdapter(AnyHttpUrl).validate_python("http://127.0.0.1:9000"),
            minio_access_key="local-user",
            minio_secret_key=SecretStr("local-password"),
        )
