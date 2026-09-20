"""S3-compatible versioned model artifact upload and startup download."""

from __future__ import annotations

import json
import shutil
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit
from uuid import uuid4

import boto3
from botocore.exceptions import ClientError

from guardrail_mini.core.config import Settings
from guardrail_mini.models.artifacts import MANIFEST_NAME, sha256_file, verify_model_artifact

if TYPE_CHECKING:
    from guardrail_mini.models.registry import ModelArtifactSpec


class S3ArtifactStore:
    """Store immutable, versioned model directories in MinIO through the S3 API."""

    def __init__(self, settings: Settings) -> None:
        if (
            settings.minio_endpoint_url is None
            or settings.minio_access_key is None
            or settings.minio_secret_key is None
        ):
            raise ValueError("MinIO endpoint and credentials must be configured.")
        self.bucket = settings.minio_bucket
        self._client: Any = boto3.client(
            "s3",
            endpoint_url=str(settings.minio_endpoint_url),
            aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key.get_secret_value(),
            region_name="us-east-1",
        )

    def close(self) -> None:
        """Close the underlying HTTP session."""

        self._client.close()

    def ensure_bucket(self) -> None:
        """Create the model bucket when absent and enable server-side version history."""

        try:
            self._client.head_bucket(Bucket=self.bucket)
        except ClientError as error:
            code = str(error.response.get("Error", {}).get("Code", ""))
            status_code = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if code not in {"404", "NoSuchBucket", "NotFound"} and status_code != 404:
                raise
            self._client.create_bucket(Bucket=self.bucket)
        self._client.put_bucket_versioning(
            Bucket=self.bucket,
            VersioningConfiguration={"Status": "Enabled"},
        )

    def upload_model(self, spec: ModelArtifactSpec, source_dir: Path) -> tuple[str, str]:
        """Upload only checksummed model files and return the URI and manifest digest."""

        manifest = verify_model_artifact(source_dir, spec.model_id, spec.revision)
        _validate_manifest_metadata(manifest, spec)
        manifest_path = source_dir / MANIFEST_NAME
        manifest_checksum = sha256_file(manifest_path)
        prefix = _model_prefix(spec)
        filenames = sorted([*manifest["files"], MANIFEST_NAME])
        for filename in filenames:
            if not isinstance(filename, str) or not _safe_relative_path(filename):
                raise ValueError("Model manifest contains an unsafe object path.")
            source_path = source_dir / filename
            digest = sha256_file(source_path)
            object_key = f"{prefix}/{filename}"
            if self._object_exists_with_checksum(object_key, digest):
                continue
            self._client.upload_file(
                str(source_path),
                self.bucket,
                object_key,
                ExtraArgs={"Metadata": {"sha256": digest}},
            )
        return f"s3://{self.bucket}/{prefix}", manifest_checksum

    def _object_exists_with_checksum(self, object_key: str, digest: str) -> bool:
        try:
            response = self._client.head_object(Bucket=self.bucket, Key=object_key)
        except ClientError as error:
            code = str(error.response.get("Error", {}).get("Code", ""))
            status_code = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if code in {"404", "NoSuchKey", "NotFound"} or status_code == 404:
                return False
            raise
        remote_digest = response.get("Metadata", {}).get("sha256")
        if remote_digest != digest:
            raise ValueError(
                f"Refusing to overwrite immutable model artifact {object_key} with different bytes."
            )
        return True

    def download_model(
        self,
        spec: ModelArtifactSpec,
        artifact_uri: str,
        manifest_checksum: str,
        cache_root: Path,
    ) -> Path:
        """Fetch one registered model to a verified local cache before serving traffic."""

        bucket, prefix = _parse_artifact_uri(artifact_uri, self.bucket, spec)
        if not _is_sha256_digest(manifest_checksum):
            raise ValueError("The model registry checksum must be a SHA-256 hex digest.")
        destination = cache_root / spec.policy_id / spec.model_version / manifest_checksum[:16]
        if _cache_is_valid(destination, spec, manifest_checksum):
            return destination

        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = destination.parent / f".{destination.name}.staging-{uuid4().hex}"
        staging.mkdir()
        try:
            manifest_path = staging / MANIFEST_NAME
            self._client.download_file(bucket, f"{prefix}/{MANIFEST_NAME}", str(manifest_path))
            if sha256_file(manifest_path) != manifest_checksum:
                raise ValueError("The model registry manifest checksum does not match PostgreSQL.")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            _validate_manifest_metadata(manifest, spec)
            files = manifest.get("files")
            if not isinstance(files, dict) or not files:
                raise ValueError("The model manifest has no checksum entries.")
            for filename in files:
                if not isinstance(filename, str) or not _safe_relative_path(filename):
                    raise ValueError("Model manifest contains an unsafe object path.")
                artifact_path = staging / filename
                artifact_path.parent.mkdir(parents=True, exist_ok=True)
                self._client.download_file(bucket, f"{prefix}/{filename}", str(artifact_path))
            verify_model_artifact(staging, spec.model_id, spec.revision)
            if destination.exists():
                shutil.rmtree(destination)
            staging.replace(destination)
            return destination
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise


def _model_prefix(spec: ModelArtifactSpec) -> str:
    return f"models/{spec.model_id}/{spec.model_version}"


def _safe_relative_path(filename: str) -> bool:
    path = PurePosixPath(filename)
    windows_path = PureWindowsPath(filename)
    return (
        "\\" not in filename
        and not path.is_absolute()
        and not windows_path.is_absolute()
        and all(part not in {"", ".", ".."} for part in path.parts)
        and all(part not in {"", ".", ".."} for part in windows_path.parts)
    )


def _is_sha256_digest(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _validate_manifest_metadata(manifest: dict[str, Any], spec: ModelArtifactSpec) -> None:
    if manifest.get("model_version") != spec.model_version:
        raise ValueError("Model manifest version does not match its registry record.")
    if manifest.get("framework") != spec.framework:
        raise ValueError("Model manifest framework does not match its registry record.")


def _parse_artifact_uri(
    artifact_uri: str,
    expected_bucket: str,
    spec: ModelArtifactSpec,
) -> tuple[str, str]:
    parsed = urlsplit(artifact_uri)
    expected_prefix = _model_prefix(spec)
    prefix = parsed.path.lstrip("/").rstrip("/")
    if parsed.scheme != "s3" or parsed.netloc != expected_bucket or prefix != expected_prefix:
        raise ValueError(f"Unexpected model artifact URI in the registry: {artifact_uri}")
    return parsed.netloc, prefix


def _cache_is_valid(destination: Path, spec: ModelArtifactSpec, manifest_checksum: str) -> bool:
    try:
        if not _is_sha256_digest(manifest_checksum):
            return False
        if sha256_file(destination / MANIFEST_NAME) != manifest_checksum:
            return False
        manifest = verify_model_artifact(destination, spec.model_id, spec.revision)
        _validate_manifest_metadata(manifest, spec)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    return True
