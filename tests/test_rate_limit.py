"""Per-project request limit tests."""

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from guardrail_mini.auth.keys import ApiKeyPrincipal
from guardrail_mini.auth.rate_limit import ProjectRateLimiter
from guardrail_mini.core.config import Settings
from guardrail_mini.core.errors import GuardrailError
from guardrail_mini.core.policy_engine import PolicyRegistry
from guardrail_mini.main import create_app
from guardrail_mini.policies.toxicity import ToxicityPolicy, ToxicityScore


class _StaticScorer:
    model_version = "static-test-model"

    def score(self, text: str) -> ToxicityScore:
        del text
        return ToxicityScore(score=0.1, model_version=self.model_version)


def test_project_rate_limit_and_window_reset() -> None:
    now = [10.0]
    limiter = ProjectRateLimiter(2, window_seconds=60, clock=lambda: now[0])
    project_id = uuid4()

    limiter.check(project_id)
    limiter.check(project_id)
    with pytest.raises(GuardrailError) as raised:
        limiter.check(project_id)

    assert raised.value.status_code == 429
    assert raised.value.code == "RATE_LIMITED"
    assert raised.value.headers == {"Retry-After": "60"}

    now[0] = 70.0
    limiter.check(project_id)


def test_project_rate_limit_is_scoped_by_project() -> None:
    limiter = ProjectRateLimiter(1)
    limiter.check(uuid4())
    limiter.check(uuid4())


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_rate_limit_error_is_returned_by_authenticated_evaluate_api() -> None:
    settings = Settings(_env_file=None, rate_limit_requests_per_minute=1)  # type: ignore[call-arg]
    app = create_app(settings)
    principal = ApiKeyPrincipal(uuid4(), uuid4(), uuid4(), None)

    class _Authenticator:
        def authenticate(self, raw_key: str) -> ApiKeyPrincipal:
            assert raw_key == "test-key"
            return principal

    app.state.api_key_authenticator = _Authenticator()
    app.state.policy_registry = PolicyRegistry(
        [ToxicityPolicy(_StaticScorer(), threshold=0.8, review_threshold=0.55)]
    )
    headers = {"Authorization": "Bearer test-key"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(
            "/v1/guardrails/evaluate", json={"input": "A safe example."}, headers=headers
        )
        limited = await client.post(
            "/v1/guardrails/evaluate", json={"input": "A second example."}, headers=headers
        )

    assert first.status_code == 200
    assert limited.status_code == 429
    assert limited.headers["Retry-After"]
    assert limited.json()["error"]["code"] == "RATE_LIMITED"
