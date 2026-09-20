"""Public, tightly bounded playground routes for the recruiter demo."""

from hashlib import sha256
from pathlib import Path
from time import perf_counter
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from guardrail_mini.auth.rate_limit import ProjectRateLimiter
from guardrail_mini.core.config import Settings
from guardrail_mini.core.errors import GuardrailError
from guardrail_mini.core.policy_engine import PolicyAction, PolicyRegistry

router = APIRouter(tags=["demo"])
DEMO_PAGE = Path(__file__).resolve().parents[2] / "static" / "demo.html"
DemoPolicyId = Literal["toxicity", "pii", "prompt_injection"]


def _default_policies() -> list[DemoPolicyId]:
    return ["toxicity", "pii", "prompt_injection"]


class DemoEvaluateRequest(BaseModel):
    """Bounded text and policy selection for the unauthenticated demo."""

    input: str = Field(min_length=1, max_length=2_000)
    policies: list[DemoPolicyId] = Field(
        default_factory=_default_policies, min_length=1, max_length=3
    )


class DemoPolicyResult(BaseModel):
    score: float
    threshold: float
    review_threshold: float | None
    action: PolicyAction
    categories: list[str]
    model_version: str


class DemoEvaluateResponse(BaseModel):
    request_id: str
    action: PolicyAction
    decision_strategy: Literal["ANY_BLOCK"] = "ANY_BLOCK"
    policy_results: dict[str, DemoPolicyResult]
    latency_ms: float
    input_chars: int
    input_stored: Literal[False] = False


def _ensure_demo_enabled(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    if not settings.demo_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
    return settings


@router.get("/demo", response_class=HTMLResponse, include_in_schema=False)
def demo_page(request: Request) -> HTMLResponse:
    """Serve the interactive playground when the optional demo is enabled."""

    _ensure_demo_enabled(request)
    return HTMLResponse(DEMO_PAGE.read_text(encoding="utf-8"))


@router.post("/v1/demo/evaluate", response_model=DemoEvaluateResponse)
def evaluate_demo(request: Request, body: DemoEvaluateRequest) -> DemoEvaluateResponse:
    """Run selected policies without requiring a visitor to hold a private API key."""

    _ensure_demo_enabled(request)
    registry: PolicyRegistry | None = getattr(request.app.state, "policy_registry", None)
    if registry is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The policy engine is not ready.",
        )

    rate_limiter: ProjectRateLimiter | None = getattr(request.app.state, "demo_rate_limiter", None)
    if rate_limiter is None:
        raise GuardrailError(503, "MODEL_NOT_READY", "The demo is not ready for requests.")
    client_host = request.client.host if request.client is not None else "unknown"
    bucket_id = UUID(bytes=sha256(client_host.encode("utf-8")).digest()[:16])
    rate_limiter.check(bucket_id)

    started = perf_counter()
    results, action = registry.evaluate(body.input, list(body.policies))
    request_id = getattr(request.state, "request_id", f"req_{uuid4().hex}")
    return DemoEvaluateResponse(
        request_id=request_id,
        action=action,
        policy_results={
            result.policy_id: DemoPolicyResult(
                score=result.score,
                threshold=result.threshold,
                review_threshold=registry.get_policy(result.policy_id).review_threshold,
                action=result.action,
                categories=list(result.categories),
                model_version=result.model_version,
            )
            for result in results
        },
        latency_ms=(perf_counter() - started) * 1000,
        input_chars=len(body.input),
    )
