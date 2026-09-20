"""Health, liveness, and readiness endpoints."""

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class StatusResponse(BaseModel):
    status: str


@router.get("/health", response_model=StatusResponse)
def health() -> StatusResponse:
    """Report that the process can serve HTTP requests."""

    return StatusResponse(status="healthy")


@router.get("/live", response_model=StatusResponse)
def live() -> StatusResponse:
    """Report that the process is alive and should not be restarted."""

    return StatusResponse(status="alive")


@router.get("/ready", response_model=StatusResponse)
def ready(request: Request) -> StatusResponse:
    """Report whether startup completed and the app can accept work."""

    if not getattr(request.app.state, "ready", False):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Application startup is not complete",
        )
    return StatusResponse(status="ready")
