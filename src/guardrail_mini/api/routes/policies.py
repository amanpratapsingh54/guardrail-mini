"""Read-only policy catalog endpoints."""

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from guardrail_mini.core.policy_engine import PolicyMetadata, PolicyRegistry

router = APIRouter(prefix="/v1/policies", tags=["policies"])


class PolicyResponse(BaseModel):
    id: str
    name: str
    version: str
    threshold: float
    review_threshold: float | None
    severity: int
    enabled: bool


def _registry(request: Request) -> PolicyRegistry:
    registry: PolicyRegistry | None = getattr(request.app.state, "policy_registry", None)
    if registry is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The policy engine is not ready.",
        )
    return registry


def _to_response(metadata: PolicyMetadata) -> PolicyResponse:
    return PolicyResponse(**metadata.__dict__)


@router.get("", response_model=list[PolicyResponse])
def list_policies(request: Request) -> list[PolicyResponse]:
    """List the enabled and disabled policy definitions in this process."""

    return [_to_response(policy) for policy in _registry(request).list_policies()]


@router.get("/{policy_id}", response_model=PolicyResponse)
def get_policy(policy_id: str, request: Request) -> PolicyResponse:
    """Return metadata for one policy ID."""

    return _to_response(_registry(request).get_policy(policy_id))
