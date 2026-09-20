"""Download the pinned Wolf Defender Small prompt-injection classifier."""

import json
from pathlib import Path

from huggingface_hub import HfApi, snapshot_download

from guardrail_mini.models.artifacts import MANIFEST_NAME, sha256_file
from guardrail_mini.policies.prompt_injection import MODEL_ID, MODEL_REVISION

MODEL_DIR = Path("models/prompt-injection/v1")
MODEL_FILES = (
    "LICENSE",
    "config.json",
    "model.safetensors",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
)


def main() -> None:
    info = HfApi().model_info(MODEL_ID, revision=MODEL_REVISION)
    if info.sha != MODEL_REVISION:
        raise RuntimeError(f"Expected pinned revision {MODEL_REVISION}, got {info.sha}.")
    license_name = getattr(info.card_data, "license", None)
    if license_name != "apache-2.0":
        raise RuntimeError(f"Expected Apache-2.0 model license, got {license_name!r}.")

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=MODEL_ID,
        revision=MODEL_REVISION,
        local_dir=MODEL_DIR,
        allow_patterns=list(MODEL_FILES),
    )
    manifest = {
        "model_id": MODEL_ID,
        "model_version": "v1",
        "revision": MODEL_REVISION,
        "license": license_name,
        "framework": "transformers-pytorch-safetensors",
        "files": {filename: sha256_file(MODEL_DIR / filename) for filename in MODEL_FILES},
    }
    manifest_path = MODEL_DIR / MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Downloaded {MODEL_ID}@{MODEL_REVISION} to {MODEL_DIR}")
    print(f"Wrote checksums to {manifest_path}")


if __name__ == "__main__":
    main()
