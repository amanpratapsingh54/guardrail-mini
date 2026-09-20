"""Unit tests for deterministic policy action aggregation."""

import pytest

from guardrail_mini.core.policy_engine import (
    AggregationStrategy,
    PolicyAction,
    PolicyResult,
    aggregate_decisions,
)


def result(policy_id: str, action: PolicyAction, severity: int) -> PolicyResult:
    return PolicyResult(
        policy_id=policy_id,
        score=0.9,
        threshold=0.8,
        action=action,
        model_version="test-version",
        severity=severity,
    )


@pytest.mark.parametrize(
    ("actions", "expected"),
    [
        ([PolicyAction.ALLOW, PolicyAction.ALLOW], PolicyAction.ALLOW),
        ([PolicyAction.ALLOW, PolicyAction.REVIEW], PolicyAction.REVIEW),
        ([PolicyAction.REVIEW, PolicyAction.BLOCK], PolicyAction.BLOCK),
    ],
)
def test_any_block_aggregation(actions: list[PolicyAction], expected: PolicyAction) -> None:
    results = [
        result(f"policy-{index}", action, severity=1) for index, action in enumerate(actions)
    ]
    assert aggregate_decisions(results) == expected


def test_highest_severity_strategy_selects_the_highest_severity_policy() -> None:
    results = [
        result("low", PolicyAction.BLOCK, severity=1),
        result("high", PolicyAction.REVIEW, severity=3),
    ]
    assert aggregate_decisions(results, AggregationStrategy.HIGHEST_SEVERITY) == PolicyAction.REVIEW


def test_aggregation_requires_at_least_one_result() -> None:
    with pytest.raises(ValueError, match="At least one policy result"):
        aggregate_decisions([])
