"""Smoke tests for the Phase 1 HTTP endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from guardrail_mini.main import create_app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_health_liveness_and_readiness() -> None:
    app = create_app()
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/health")).json() == {"status": "healthy"}
            assert (await client.get("/live")).json() == {"status": "alive"}
            assert (await client.get("/ready")).json() == {"status": "ready"}
