"""Upload pinned local models to MinIO and register their versions in PostgreSQL."""

from sqlalchemy import select

from guardrail_mini.core.config import get_settings
from guardrail_mini.db.models import ModelVersion
from guardrail_mini.db.session import create_database_engine, create_session_factory
from guardrail_mini.models.artifact_store import S3ArtifactStore
from guardrail_mini.models.registry import MODEL_ARTIFACTS


def main() -> None:
    settings = get_settings()
    if settings.database_url is None:
        raise RuntimeError("Set GUARDRAIL_DATABASE_URL in .env before uploading models.")
    if settings.minio_endpoint_url is None:
        raise RuntimeError("Configure the MinIO endpoint and credentials in .env.")

    engine = create_database_engine(settings.database_url)
    factory = create_session_factory(engine)
    store = S3ArtifactStore(settings)
    try:
        store.ensure_bucket()
        for spec in MODEL_ARTIFACTS:
            artifact_uri, checksum = store.upload_model(spec, spec.local_directory(settings))
            with factory.begin() as session:
                existing = session.scalar(
                    select(ModelVersion).where(
                        ModelVersion.model_id == spec.model_id,
                        ModelVersion.version == spec.model_version,
                    )
                )
                if existing is not None:
                    if (
                        existing.artifact_uri != artifact_uri
                        or existing.checksum != checksum
                        or existing.framework != spec.framework
                    ):
                        raise ValueError(
                            f"Model version {spec.model_id}@{spec.model_version} is immutable."
                        )
                else:
                    session.add(
                        ModelVersion(
                            model_id=spec.model_id,
                            version=spec.model_version,
                            framework=spec.framework,
                            artifact_uri=artifact_uri,
                            checksum=checksum,
                        )
                    )
            print(f"Registered {spec.model_id}@{spec.model_version} at {artifact_uri}")
    finally:
        store.close()
        engine.dispose()


if __name__ == "__main__":
    main()
