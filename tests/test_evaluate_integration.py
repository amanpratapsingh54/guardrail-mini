"""End-to-end inference checks using the downloaded real toxicity model."""

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from guardrail_mini.core.config import Settings
from guardrail_mini.main import create_app
from guardrail_mini.policies.toxicity import MODEL_ID, MODEL_REVISION


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_real_toxicity_inference_and_threshold_decision() -> None:
    settings = Settings(
        toxicity_model_dir=Path("models/toxicity/v1"),
        model_device="cpu",
        toxicity_threshold=0.8,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            safe_response = await client.post(
                "/v1/guardrails/evaluate",
                json={"input": "Thank you for your thoughtful help."},
            )
            toxic_response = await client.post(
                "/v1/guardrails/evaluate",
                json={"input": "I hate you, you are awful and deserve to get hurt."},
            )

    assert safe_response.status_code == 200
    assert toxic_response.status_code == 200
    safe_result = safe_response.json()
    toxic_result = toxic_response.json()
    assert safe_result["action"] == "ALLOW"
    assert toxic_result["action"] == "BLOCK"
    assert 0.0 <= safe_result["policy_results"]["toxicity"]["score"] < 0.8
    assert toxic_result["policy_results"]["toxicity"]["score"] >= 0.8
    assert safe_result["model_versions"]["toxicity"] == f"{MODEL_ID}@{MODEL_REVISION}"
    assert safe_result["request_id"].startswith("req_")
    assert toxic_result["latency_ms"] > 0
