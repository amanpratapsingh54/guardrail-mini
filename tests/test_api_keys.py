"""Bearer authentication and project-scoped key management integration tests."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from guardrail_mini.auth.keys import ApiKeyAuthenticator, hash_api_key, issue_api_key
from guardrail_mini.core.config import Settings
from guardrail_mini.core.policy_engine import PolicyRegistry
from guardrail_mini.db.base import Base
from guardrail_mini.db.models import ApiKey, Project, Tenant
from guardrail_mini.db.session import create_database_engine, create_session_factory
from guardrail_mini.main import create_app
from guardrail_mini.policies.toxicity import ToxicityPolicy, ToxicityScore


class _StaticToxicityScorer:
    model_version = "static-test-model"

    def score(self, text: str) -> ToxicityScore:
        return ToxicityScore(score=0.1, model_version=self.model_version)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_authenticated_evaluation_and_project_scoped_key_lifecycle(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'api-keys.db'}"
    engine = create_database_engine(database_url)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    base_key = "gr_live_initial_project_key"
    expired_key = "gr_live_expired_project_key"

    with factory.begin() as session:
        tenant = Tenant(name="tenant one")
        project = Project(name="project one", tenant=tenant)
        other_tenant = Tenant(name="tenant two")
        other_project = Project(name="project two", tenant=other_tenant)
        session.add_all([tenant, project, other_tenant, other_project])
        session.flush()
        # Use the known integration token so the HTTP header is deterministic.
        session.add(
            ApiKey(
                project_id=project.id,
                name="known initial",
                key_prefix=base_key[:16],
                key_hash=hash_api_key(base_key),
            )
        )
        expired_record = ApiKey(
            project_id=project.id,
            name="expired",
            key_prefix=expired_key[:16],
            key_hash=hash_api_key(expired_key),
            expires_at=datetime.now(UTC) - timedelta(days=1),
        )
        other_key, _ = issue_api_key(session, other_project.id, "other project")
        session.add(expired_record)
        session.flush()
        other_key_id = other_key.id
        tenant_id = tenant.id
        project_id = project.id

    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    app = create_app(settings)
    app.state.database_session_factory = factory
    app.state.api_key_authenticator = ApiKeyAuthenticator(factory)
    app.state.policy_registry = PolicyRegistry(
        [ToxicityPolicy(_StaticToxicityScorer(), threshold=0.8, review_threshold=0.5)]
    )
    app.state.ready = True

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        unauthenticated = await client.post("/v1/guardrails/evaluate", json={"input": "hello"})
        invalid = await client.post(
            "/v1/guardrails/evaluate",
            json={"input": "hello"},
            headers={"Authorization": "Bearer invalid-key"},
        )
        expired = await client.post(
            "/v1/guardrails/evaluate",
            json={"input": "hello"},
            headers={"Authorization": f"Bearer {expired_key}"},
        )
        headers = {"Authorization": f"Bearer {base_key}"}
        evaluated = await client.post(
            "/v1/guardrails/evaluate", json={"input": "A neutral request."}, headers=headers
        )
        created = await client.post(
            "/v1/api-keys",
            json={"name": "rotation key", "expires_in_days": 14},
            headers=headers,
        )

        assert created.status_code == 201, created.text
        created_body = created.json()
        raw_key = created_body["api_key"]
        created_id = UUID(created_body["id"])
        with factory() as session:
            stored = session.get(ApiKey, created_id)
            assert stored is not None
            assert stored.key_hash == hash_api_key(raw_key)
            assert raw_key not in stored.key_hash
            assert stored.expires_at is not None

        cross_project_revoke = await client.delete(f"/v1/api-keys/{other_key_id}", headers=headers)
        revoked = await client.delete(f"/v1/api-keys/{created_id}", headers=headers)
        revoked_key_evaluation = await client.post(
            "/v1/guardrails/evaluate",
            json={"input": "hello"},
            headers={"Authorization": f"Bearer {raw_key}"},
        )

    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["error"]["code"] == "AUTHENTICATION_FAILED"
    assert invalid.status_code == 401
    assert expired.status_code == 401
    assert evaluated.status_code == 200
    assert evaluated.json()["action"] == "ALLOW"
    assert evaluated.json()["tenant_id"] == str(tenant_id)
    assert evaluated.json()["project_id"] == str(project_id)
    assert created_body["key_prefix"] == raw_key[:16]
    assert created_body["expires_at"] is not None
    assert cross_project_revoke.status_code == 404
    assert cross_project_revoke.json()["error"]["code"] == "API_KEY_NOT_FOUND"
    assert revoked.status_code == 200
    assert revoked.json() == {"id": str(created_id), "status": "revoked"}
    assert revoked_key_evaluation.status_code == 401
    with factory() as session:
        assert session.scalar(
            select(ApiKey.last_used_at).where(ApiKey.key_hash == hash_api_key(base_key))
        )

    engine.dispose()
