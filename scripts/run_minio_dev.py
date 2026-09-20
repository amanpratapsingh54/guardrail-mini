"""Run the local MinIO server using the same credentials as the API settings."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from guardrail_mini.core.config import get_settings


def _find_minio_executable() -> Path:
    local_executable = Path(sys.executable).with_name("minio")
    if local_executable.is_file():
        return local_executable
    path_executable = shutil.which("minio")
    if path_executable is not None:
        return Path(path_executable)
    raise FileNotFoundError(
        "MinIO executable is missing. See docs/MODEL_REGISTRY.md for the pinned source build."
    )


def main() -> None:
    settings = get_settings()
    if (
        settings.minio_endpoint_url is None
        or settings.minio_access_key is None
        or settings.minio_secret_key is None
    ):
        raise RuntimeError("Set the MinIO endpoint and both credentials in .env first.")

    endpoint = settings.minio_endpoint_url
    if endpoint.host is None or endpoint.scheme not in {"http", "https"}:
        raise ValueError("The MinIO endpoint must include an HTTP(S) host.")
    port = endpoint.port or (443 if endpoint.scheme == "https" else 9000)
    bind_address = f"{endpoint.host}:{port}"
    data_dir = Path("data/minio-data")
    data_dir.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["MINIO_ROOT_USER"] = settings.minio_access_key
    environment["MINIO_ROOT_PASSWORD"] = settings.minio_secret_key.get_secret_value()

    command = [
        str(_find_minio_executable()),
        "server",
        "--address",
        bind_address,
        "--console-address",
        "127.0.0.1:9001",
        str(data_dir),
    ]
    print(f"Starting local MinIO at {settings.minio_endpoint_url}; press Ctrl+C to stop.")
    raise SystemExit(subprocess.run(command, env=environment, check=False).returncode)


if __name__ == "__main__":
    main()
