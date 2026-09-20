"""Model artifact URI and path validation tests."""

import pytest

from guardrail_mini.models.artifact_store import _parse_artifact_uri, _safe_relative_path
from guardrail_mini.models.registry import MODEL_ARTIFACTS


def test_registered_artifact_uri_is_bucket_and_version_scoped() -> None:
    spec = MODEL_ARTIFACTS[0]
    assert _parse_artifact_uri(
        "s3://guardrail-models/models/unitary/toxic-bert/v1",
        "guardrail-models",
        spec,
    ) == ("guardrail-models", "models/unitary/toxic-bert/v1")


@pytest.mark.parametrize(
    "artifact_uri",
    [
        "https://other-bucket/models/unitary/toxic-bert/v1",
        "s3://other-bucket/models/unitary/toxic-bert/v1",
        "s3://guardrail-models/models/unitary/toxic-bert/v2",
    ],
)
def test_unexpected_artifact_uri_is_rejected(artifact_uri: str) -> None:
    with pytest.raises(ValueError, match="Unexpected model artifact URI"):
        _parse_artifact_uri(artifact_uri, "guardrail-models", MODEL_ARTIFACTS[0])


@pytest.mark.parametrize("filename", ["../secret", "/absolute/file", "nested/../../escape"])
def test_manifest_paths_cannot_escape_model_directory(filename: str) -> None:
    assert not _safe_relative_path(filename)


def test_manifest_paths_allow_subdirectories() -> None:
    assert _safe_relative_path("tokenizer/data.json")


def test_manifest_paths_reject_windows_separators_and_drives() -> None:
    assert not _safe_relative_path(r"..\secret")
    assert not _safe_relative_path(r"C:\models\weights.bin")
