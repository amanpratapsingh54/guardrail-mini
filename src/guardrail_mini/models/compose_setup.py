"""Helpers for preparing model artifacts in the local Compose stack."""

import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

from guardrail_mini.core.config import get_settings

READY_TIMEOUT_SECONDS = 180


def wait_for_minio(endpoint: str) -> None:
    """Wait for the MinIO readiness endpoint before uploading model artifacts."""

    health_url = f"{endpoint.rstrip('/')}/minio/health/ready"
    deadline = time.monotonic() + READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            with urlopen(health_url, timeout=3) as response:
                if 200 <= response.status < 300:
                    return
        except (OSError, TimeoutError, URLError):
            time.sleep(2)
    raise TimeoutError(f"MinIO did not become ready within {READY_TIMEOUT_SECONDS} seconds.")


def run_script(script_name: str) -> None:
    subprocess.run([sys.executable, f"scripts/{script_name}"], check=True)


def main() -> None:
    settings = get_settings()
    if settings.minio_endpoint_url is None:
        raise RuntimeError("GUARDRAIL_MINIO_ENDPOINT_URL is required for Compose model setup.")

    wait_for_minio(str(settings.minio_endpoint_url))
    if not (settings.toxicity_model_dir / "manifest.json").is_file():
        run_script("download_model.py")
    if not (settings.prompt_injection_model_dir / "manifest.json").is_file():
        run_script("download_prompt_injection_model.py")
    run_script("upload_models_to_minio.py")
