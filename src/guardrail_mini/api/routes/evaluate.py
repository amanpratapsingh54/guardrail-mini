"""Initial single-policy inference endpoint."""

from collections.abc import Callable
from time import perf_counter
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from guardrail_mini.api.auth import get_authenticated_project
from guardrail_mini.auth.keys import ApiKeyPrincipal
from guardrail_mini.core.config import Settings
from guardrail_mini.core.policy_engine import PolicyAction, PolicyRegistry, PolicyResult
from guardrail_mini.policies.toxicity import ToxicityClassifier

router = APIRouter(prefix="/v1/guardrails", tags=["guardrails"])


class EvaluateRequest(BaseModel):
    """Text and policy selection submitted for evaluation."""

    input: str = Field(min_length=1, max_length=10_000)
    policies: list[str] = Field(default_factory=lambda: ["toxicity"], min_length=1, max_length=10)


class PolicyResultResponse(BaseModel):
    score: float
    threshold: float
    action: PolicyAction
    categories: list[str] = Field(default_factory=list)


class EvaluateResponse(BaseModel):
    request_id: str
    tenant_id: UUID
    project_id: UUID
    action: PolicyAction
    policy_results: dict[str, PolicyResultResponse]
    model_versions: dict[str, str]
    latency_ms: float


ModelLoader = Callable[[Settings], ToxicityClassifier]


def load_model_from_settings(settings: Settings) -> ToxicityClassifier:
    """Load and warm up the local toxicity artifact selected by settings."""

    from guardrail_mini.policies.toxicity import load_toxicity_classifier

    return load_toxicity_classifier(settings.toxicity_model_dir, settings.model_device)


@router.post("/evaluate", response_model=EvaluateResponse)
def evaluate(
    request: Request,
    body: EvaluateRequest,
    principal: Annotated[ApiKeyPrincipal, Depends(get_authenticated_project)],
) -> EvaluateResponse:
    """Evaluate the requested policies and aggregate their actions."""

    started = perf_counter()
    registry: PolicyRegistry | None = getattr(request.app.state, "policy_registry", None)
    if registry is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The policy engine is not ready.",
        )

    results, action = registry.evaluate(body.input, body.policies)
    request_id = f"req_{uuid4().hex}"
    return EvaluateResponse(
        request_id=request_id,
        tenant_id=principal.tenant_id,
        project_id=principal.project_id,
        action=action,
        policy_results={result.policy_id: _to_response(result) for result in results},
        model_versions={result.policy_id: result.model_version for result in results},
        latency_ms=(perf_counter() - started) * 1000,
    )


def _to_response(result: PolicyResult) -> PolicyResultResponse:
    return PolicyResultResponse(
        score=result.score,
        threshold=result.threshold,
        action=result.action,
        categories=list(result.categories),
    )
