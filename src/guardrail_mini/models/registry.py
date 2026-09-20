"""Versioned model metadata lookup and local startup cache preparation."""

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from guardrail_mini.core.config import Settings
from guardrail_mini.db.models import ModelVersion
from guardrail_mini.db.session import create_database_engine, create_session_factory
from guardrail_mini.models.artifact_store import S3ArtifactStore
from guardrail_mini.policies.prompt_injection import (
    MODEL_ID as PROMPT_INJECTION_MODEL_ID,
)
from guardrail_mini.policies.prompt_injection import (
    MODEL_REVISION as PROMPT_INJECTION_MODEL_REVISION,
)
from guardrail_mini.policies.toxicity import MODEL_ID as TOXICITY_MODEL_ID
from guardrail_mini.policies.toxicity import MODEL_REVISION as TOXICITY_MODEL_REVISION

MODEL_VERSION = "v1"


@dataclass(frozen=True)
class ModelArtifactSpec:
    """The approved identity and local settings field for one served model."""

    policy_id: str
    model_id: str
    revision: str
    model_version: str
    framework: str = "transformers-pytorch-safetensors"

    def local_directory(self, settings: Settings) -> Path:
        if self.policy_id == "toxicity":
            return settings.toxicity_model_dir
        if self.policy_id == "prompt_injection":
            return settings.prompt_injection_model_dir
        raise ValueError(f"Unsupported model policy ID: {self.policy_id}")


MODEL_ARTIFACTS = (
    ModelArtifactSpec("toxicity", TOXICITY_MODEL_ID, TOXICITY_MODEL_REVISION, MODEL_VERSION),
    ModelArtifactSpec(
        "prompt_injection",
        PROMPT_INJECTION_MODEL_ID,
        PROMPT_INJECTION_MODEL_REVISION,
        MODEL_VERSION,
    ),
)


def resolve_model_directories(
    settings: Settings,
    session_factory: sessionmaker[Session] | None = None,
) -> dict[str, Path]:
    """Return local paths or fetch the registered immutable artifacts before startup."""

    if settings.minio_endpoint_url is None:
        return {spec.policy_id: spec.local_directory(settings) for spec in MODEL_ARTIFACTS}

    if settings.database_url is None or settings.minio_access_key is None:
        raise ValueError("Database and MinIO credentials must be configured together.")
    if settings.minio_secret_key is None:
        raise ValueError("The MinIO secret key is required.")

    engine = None
    factory = session_factory
    if factory is None:
        engine = create_database_engine(settings.database_url)
        factory = create_session_factory(engine)
    store = S3ArtifactStore(settings)
    try:
        with factory() as session:
            resolved: dict[str, Path] = {}
            for spec in MODEL_ARTIFACTS:
                record = session.scalar(
                    select(ModelVersion).where(
                        ModelVersion.model_id == spec.model_id,
                        ModelVersion.version == spec.model_version,
                    )
                )
                if record is None:
                    raise RuntimeError(
                        f"No model registry record exists for "
                        f"{spec.model_id}@{spec.model_version}; "
                        "run scripts/upload_models_to_minio.py before starting the API."
                    )
                if record.framework != spec.framework:
                    raise RuntimeError(
                        f"Registry framework for {spec.model_id}@{spec.model_version} "
                        f"must be {spec.framework!r}."
                    )
                resolved[spec.policy_id] = store.download_model(
                    spec=spec,
                    artifact_uri=record.artifact_uri,
                    manifest_checksum=record.checksum,
                    cache_root=settings.artifact_cache_dir,
                )
            return resolved
    finally:
        store.close()
        if engine is not None:
            engine.dispose()
