"""Tests for the Compose one-shot model preparation service."""

from pathlib import Path

import pytest
from pydantic import AnyHttpUrl, SecretStr, TypeAdapter

from guardrail_mini.core.config import Settings
from guardrail_mini.models import compose_setup as prepare_compose_models


def test_wait_for_minio_uses_readiness_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: list[tuple[str, float]] = []

    class ReadyResponse:
        status = 200

        def __enter__(self) -> "ReadyResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    def urlopen(url: str, timeout: float) -> ReadyResponse:
        observed.append((url, timeout))
        return ReadyResponse()

    monkeypatch.setattr(prepare_compose_models, "urlopen", urlopen)

    prepare_compose_models.wait_for_minio("http://minio:9000/")

    assert observed == [("http://minio:9000/minio/health/ready", 3)]


def test_main_downloads_only_missing_model_manifests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    toxicity_dir = tmp_path / "toxicity"
    prompt_dir = tmp_path / "prompt-injection"
    toxicity_dir.mkdir()
    prompt_dir.mkdir()
    (toxicity_dir / "manifest.json").write_text("{}", encoding="utf-8")
    endpoint = TypeAdapter(AnyHttpUrl).validate_python("http://minio:9000")
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        database_url="sqlite:///compose-setup-test.db",
        minio_endpoint_url=endpoint,
        minio_access_key="local-user",
        minio_secret_key=SecretStr("local-password"),
    )
    settings.toxicity_model_dir = toxicity_dir
    settings.prompt_injection_model_dir = prompt_dir
    waits: list[str] = []
    scripts: list[str] = []
    monkeypatch.setattr(prepare_compose_models, "get_settings", lambda: settings)
    monkeypatch.setattr(prepare_compose_models, "wait_for_minio", waits.append)
    monkeypatch.setattr(prepare_compose_models, "run_script", scripts.append)

    prepare_compose_models.main()

    assert waits == [str(endpoint)]
    assert scripts == ["download_prompt_injection_model.py", "upload_models_to_minio.py"]
