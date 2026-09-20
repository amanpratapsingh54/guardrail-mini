"""Composable policy metadata, evaluation, and action aggregation."""

from dataclasses import dataclass
from enum import StrEnum
from time import perf_counter
from typing import Protocol

from guardrail_mini.core.errors import GuardrailError
from guardrail_mini.observability.metrics import POLICY_EVALUATIONS_TOTAL, POLICY_LATENCY_SECONDS


class PolicyAction(StrEnum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    REVIEW = "REVIEW"


class AggregationStrategy(StrEnum):
    ANY_BLOCK = "ANY_BLOCK"
    HIGHEST_SEVERITY = "HIGHEST_SEVERITY"


@dataclass(frozen=True)
class PolicyMetadata:
    id: str
    name: str
    version: str
    threshold: float
    review_threshold: float | None
    severity: int
    enabled: bool = True


@dataclass(frozen=True)
class PolicyResult:
    policy_id: str
    score: float
    threshold: float
    action: PolicyAction
    model_version: str
    severity: int
    categories: tuple[str, ...] = ()


class Policy(Protocol):
    """Interface implemented by each independent guardrail policy."""

    metadata: PolicyMetadata

    def evaluate(self, text: str) -> PolicyResult: ...


def aggregate_decisions(
    results: list[PolicyResult],
    strategy: AggregationStrategy = AggregationStrategy.ANY_BLOCK,
) -> PolicyAction:
    """Combine policy outcomes while preserving a simple extension point."""

    if not results:
        raise ValueError("At least one policy result is required for aggregation.")

    if strategy == AggregationStrategy.ANY_BLOCK:
        if any(result.action == PolicyAction.BLOCK for result in results):
            return PolicyAction.BLOCK
        if any(result.action == PolicyAction.REVIEW for result in results):
            return PolicyAction.REVIEW
        return PolicyAction.ALLOW

    return max(
        results,
        key=lambda result: (
            result.severity,
            {
                PolicyAction.ALLOW: 0,
                PolicyAction.REVIEW: 1,
                PolicyAction.BLOCK: 2,
            }[result.action],
        ),
    ).action


class PolicyRegistry:
    """Resolve configured policies by ID and evaluate a selected policy set."""

    def __init__(self, policies: list[Policy]) -> None:
        self._policies = {policy.metadata.id: policy for policy in policies}
        if len(self._policies) != len(policies):
            raise ValueError("Policy IDs must be unique.")

    def list_policies(self) -> list[PolicyMetadata]:
        return [policy.metadata for policy in self._policies.values()]

    def get_policy(self, policy_id: str) -> PolicyMetadata:
        policy = self._policies.get(policy_id)
        if policy is None:
            raise GuardrailError(404, "POLICY_NOT_FOUND", f"Policy '{policy_id}' does not exist.")
        return policy.metadata

    def evaluate(
        self,
        text: str,
        policy_ids: list[str],
        strategy: AggregationStrategy = AggregationStrategy.ANY_BLOCK,
    ) -> tuple[list[PolicyResult], PolicyAction]:
        if not policy_ids:
            raise GuardrailError(422, "INVALID_REQUEST", "At least one policy is required.")

        results: list[PolicyResult] = []
        for policy_id in dict.fromkeys(policy_ids):
            policy = self._policies.get(policy_id)
            if policy is None:
                raise GuardrailError(
                    404,
                    "POLICY_NOT_FOUND",
                    f"Policy '{policy_id}' does not exist.",
                )
            if not policy.metadata.enabled:
                raise GuardrailError(
                    409,
                    "POLICY_DISABLED",
                    f"Policy '{policy_id}' is disabled.",
                )
            started = perf_counter()
            try:
                try:
                    result = policy.evaluate(text)
                except TimeoutError as error:
                    raise GuardrailError(
                        504,
                        "INFERENCE_TIMEOUT",
                        "Policy inference exceeded its execution time limit.",
                    ) from error
            finally:
                POLICY_LATENCY_SECONDS.labels(policy_id=policy_id).observe(perf_counter() - started)
            POLICY_EVALUATIONS_TOTAL.labels(
                policy_id=policy_id,
                action=result.action.value,
            ).inc()
            results.append(result)

        return results, aggregate_decisions(results, strategy)
