"""Portable migration and control-plane persistence checks."""

from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select

from guardrail_mini.db.models import (
    ApiKey,
    ModelVersion,
    PolicyConfiguration,
    PolicyMetadataRecord,
    Project,
    Tenant,
)
from guardrail_mini.db.session import create_database_engine, create_session_factory


def _alembic_config(database_url: str) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("script_location", "migrations")
    config.attributes["database_url"] = database_url
    return config


def test_migrations_create_control_plane_schema_and_support_records(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'control-plane.db'}"
    config = _alembic_config(database_url)
    command.upgrade(config, "head")

    engine = create_database_engine(database_url)
    expected_tables = {
        "tenants",
        "projects",
        "api_keys",
        "policy_metadata",
        "policy_configurations",
        "model_versions",
        "alembic_version",
    }
    assert expected_tables <= set(inspect(engine).get_table_names())

    factory = create_session_factory(engine)
    tenant_id = uuid4()
    project_id = uuid4()
    with factory.begin() as session:
        tenant = Tenant(id=tenant_id, name="sample tenant")
        project = Project(id=project_id, name="sample project", tenant=tenant)
        session.add_all(
            [
                tenant,
                project,
                ApiKey(
                    project=project,
                    name="development",
                    key_prefix="gr_test",
                    key_hash="f" * 64,
                ),
                PolicyMetadataRecord(
                    policy_id="toxicity",
                    name="Toxicity",
                    version="unitary-toxic-bert@revision",
                    threshold=0.8,
                    review_threshold=0.55,
                    severity=10,
                ),
                ModelVersion(
                    model_id="unitary/toxic-bert",
                    version="revision",
                    framework="transformers",
                    artifact_uri="file://models/toxicity/v1",
                    checksum="a" * 64,
                    metrics={"source": "pinned-model-card"},
                ),
            ]
        )
        session.flush()
        session.add(
            PolicyConfiguration(
                project_id=project_id,
                policy_id="toxicity",
                threshold=0.7,
                review_threshold=0.5,
            )
        )

    with factory() as session:
        assert session.scalar(select(Tenant.name).where(Tenant.id == tenant_id)) == "sample tenant"
        assert session.scalar(select(ApiKey.is_active)) is True
        assert session.scalar(select(PolicyConfiguration.threshold)) == 0.7
        metrics = session.scalar(select(ModelVersion.metrics))
        assert metrics is not None
        assert metrics["source"] == "pinned-model-card"

    engine.dispose()
    command.downgrade(config, "base")
    assert set(inspect(engine).get_table_names()) == {"alembic_version"}
    engine.dispose()
