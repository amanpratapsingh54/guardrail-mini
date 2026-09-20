"""Request IDs, privacy-safe errors, and Prometheus exposition tests."""

import json
import logging
import re
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from guardrail_mini.auth.keys import ApiKeyPrincipal
from guardrail_mini.core.config import Settings
from guardrail_mini.main import create_app
from guardrail_mini.observability.logging import JsonFormatter, request_id_context


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_request_id_is_propagated_and_metrics_are_exposed() -> None:
    app = create_app()
    app.state.ready = True
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        health = await client.get("/health", headers={"X-Request-ID": "client-trace_123"})
        metrics = await client.get("/metrics")

    assert health.headers["X-Request-ID"] == "client-trace_123"
    assert metrics.status_code == 200
    assert "text/plain" in metrics.headers["content-type"]
    assert "guardrail_requests_total" in metrics.text
    assert "guardrail_request_duration_seconds_bucket" in metrics.text
    assert "guardrail_errors_total" in metrics.text


@pytest.mark.anyio
async def test_invalid_request_id_is_replaced_and_validation_body_is_not_reflected() -> None:
    app = create_app()
    principal = ApiKeyPrincipal(uuid4(), uuid4(), uuid4(), datetime.now(UTC))

    class _Authenticator:
        def authenticate(self, raw_key: str) -> ApiKeyPrincipal:
            assert raw_key == "test-key"
            return principal

    app.state.api_key_authenticator = _Authenticator()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/guardrails/evaluate",
            headers={"X-Request-ID": "bad request id", "Authorization": "Bearer test-key"},
            json={"input": {"secret": "private text"}},
        )

    request_id = response.headers["X-Request-ID"]
    assert re.fullmatch(r"req_[a-f0-9]{32}", request_id)
    assert response.status_code == 422
    assert response.json()["error"]["request_id"] == request_id
    assert "private text" not in response.text


@pytest.mark.anyio
async def test_unexpected_error_returns_safe_response_and_request_id() -> None:
    app = create_app()

    async def fail() -> dict[str, str]:
        raise ValueError("private request content")

    app.add_api_route("/test-error", fail)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/test-error", headers={"X-Request-ID": "failure-123"})
    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "failure-123"
    assert response.json()["error"]["request_id"] == "failure-123"
    assert "private request content" not in response.text


@pytest.mark.anyio
async def test_oversized_request_is_rejected_with_matching_request_id() -> None:
    settings = Settings(_env_file=None, max_request_body_bytes=1024)  # type: ignore[call-arg]
    app = create_app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/health",
            content=b"x" * 1025,
            headers={"X-Request-ID": "oversized-123"},
        )

    assert response.status_code == 413
    assert response.headers["X-Request-ID"] == "oversized-123"
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert response.json()["error"]["request_id"] == "oversized-123"


def test_json_log_formatter_drops_unapproved_fields_and_free_form_messages() -> None:
    token = request_id_context.set("req_log_test")
    try:
        record = logging.LogRecord(
            "guardrail_mini", logging.INFO, "", 0, "private request content", (), None
        )
        record.event = "http_request_completed"
        record.input_text = "private request content"
        formatted = JsonFormatter().format(record)
    finally:
        request_id_context.reset(token)

    entry = json.loads(formatted)
    assert entry["request_id"] == "req_log_test"
    assert entry["event"] == "http_request_completed"
    assert "input_text" not in entry
    assert "message" not in entry
    assert "private request content" not in formatted
