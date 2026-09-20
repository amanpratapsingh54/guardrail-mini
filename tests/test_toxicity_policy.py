"""Unit tests for toxicity score threshold decisions."""

import pytest

from guardrail_mini.core.policy_engine import PolicyAction
from guardrail_mini.policies.toxicity import ToxicityPolicy, ToxicityScore


class FixedScoreClassifier:
    def __init__(self, score: float) -> None:
        self._score = score

    def score(self, text: str) -> ToxicityScore:
        return ToxicityScore(
            score=self._score,
            model_version="unitary/toxic-bert@test-fixture",
        )


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0.20, PolicyAction.ALLOW),
        (0.55, PolicyAction.REVIEW),
        (0.79, PolicyAction.REVIEW),
        (0.80, PolicyAction.BLOCK),
    ],
)
def test_toxicity_threshold_action(score: float, expected: PolicyAction) -> None:
    policy = ToxicityPolicy(
        FixedScoreClassifier(score),
        threshold=0.8,
        review_threshold=0.55,
    )
    assert policy.evaluate("unit-test input").action == expected


def test_review_threshold_cannot_exceed_block_threshold() -> None:
    with pytest.raises(ValueError, match="review threshold must not exceed"):
        ToxicityPolicy(FixedScoreClassifier(0.5), threshold=0.6, review_threshold=0.7)
