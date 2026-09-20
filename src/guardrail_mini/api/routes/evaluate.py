"""Initial single-policy inference endpoint."""

from collections.abc import Callable
from time import perf_counter
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from guardrail_mini.core.config import Settings
from guardrail_mini.policies.toxicity import ToxicityClassifier

router = APIRouter(prefix="/v1/guardrails", tags=["guardrails"])


class EvaluateRequest(BaseModel):
    """Text submitted for the initial toxicity-only evaluation."""

    input: str = Field(min_length=1, max_length=10_000)


class ToxicityResult(BaseModel):
    score: float
    threshold: float
    action: Literal["ALLOW", "BLOCK"]


class EvaluateResponse(BaseModel):
    request_id: str
    action: Literal["ALLOW", "BLOCK"]
    policy_results: dict[str, ToxicityResult]
    model_versions: dict[str, str]
    latency_ms: float


ModelLoader = Callable[[Settings], ToxicityClassifier]


def load_model_from_settings(settings: Settings) -> ToxicityClassifier:
    """Load and warm up the local toxicity artifact selected by settings."""

    from guardrail_mini.policies.toxicity import load_toxicity_classifier

    return load_toxicity_classifier(settings.toxicity_model_dir, settings.model_device)


@router.post("/evaluate", response_model=EvaluateResponse)
def evaluate(request: Request, body: EvaluateRequest) -> EvaluateResponse:
    """Score text with the loaded toxicity model and apply its configured threshold."""

    started = perf_counter()
    classifier = getattr(request.app.state, "toxicity_classifier", None)
    if classifier is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The toxicity model is not ready.",
        )

    settings: Settings = request.app.state.settings
    result = classifier.score(body.input)
    action: Literal["ALLOW", "BLOCK"] = (
        "BLOCK" if result.score >= settings.toxicity_threshold else "ALLOW"
    )
    return EvaluateResponse(
        request_id=f"req_{uuid4().hex}",
        action=action,
        policy_results={
            "toxicity": ToxicityResult(
                score=result.score,
                threshold=settings.toxicity_threshold,
                action=action,
            )
        },
        model_versions={"toxicity": result.model_version},
        latency_ms=(perf_counter() - started) * 1000,
    )
