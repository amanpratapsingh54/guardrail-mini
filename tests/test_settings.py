"""Configuration validation tests."""

import pytest
from pydantic import ValidationError

from guardrail_mini.core.config import Settings


def test_review_threshold_cannot_exceed_block_threshold() -> None:
    with pytest.raises(ValidationError, match="review threshold must not exceed"):
        Settings(toxicity_threshold=0.6, toxicity_review_threshold=0.7)


def test_thresholds_can_be_configured_without_a_review_band() -> None:
    settings = Settings(toxicity_threshold=0.75, toxicity_review_threshold=None)
    assert settings.toxicity_threshold == 0.75
    assert settings.toxicity_review_threshold is None
