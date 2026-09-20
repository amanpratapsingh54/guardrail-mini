"""Shared checksum verification for downloaded model artifacts."""

import hashlib
import json
from pathlib import Path
from typing import Any

MANIFEST_NAME = "manifest.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_model_artifact(
    model_dir: Path,
    expected_model_id: str,
    expected_revision: str,
) -> dict[str, Any]:
    """Verify manifest identity and checksums before a model is loaded."""

    manifest_path = model_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"Model manifest not found at {manifest_path}; run the documented model download script."
        )

    manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("model_id") != expected_model_id
        or manifest.get("revision") != expected_revision
    ):
        raise ValueError("Model manifest does not match the pinned model revision.")

    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("Model manifest has no file checksums.")

    root = model_dir.resolve()
    for filename, expected_digest in files.items():
        if not isinstance(filename, str) or not isinstance(expected_digest, str):
            raise ValueError("Model manifest contains an invalid checksum entry.")
        artifact_path = (root / filename).resolve()
        if root not in artifact_path.parents:
            raise ValueError("Model manifest references a path outside its artifact directory.")
        if not artifact_path.is_file():
            raise FileNotFoundError(f"Model artifact file is missing: {artifact_path}")
        if sha256_file(artifact_path) != expected_digest:
            raise ValueError(f"Checksum validation failed for model artifact {artifact_path}.")

    return manifest
