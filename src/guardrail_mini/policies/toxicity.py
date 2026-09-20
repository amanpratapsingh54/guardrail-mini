"""Local toxicity classifier backed by a pinned Hugging Face artifact."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

MODEL_ID = "unitary/toxic-bert"
MODEL_REVISION = "4d6c22e74ba2fdd26bc4f7238f50766b045a0d94"
MANIFEST_NAME = "manifest.json"
MAX_TOKEN_LENGTH = 512


@dataclass(frozen=True)
class ToxicityScore:
    """The classifier's normalized toxicity score and artifact version."""

    score: float
    model_version: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_model_artifact(model_dir: Path) -> dict[str, Any]:
    """Validate local files against the download manifest and return its metadata."""

    manifest_path = model_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"Model manifest not found at {manifest_path}; run `python scripts/download_model.py`."
        )

    manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("model_id") != MODEL_ID or manifest.get("revision") != MODEL_REVISION:
        raise ValueError("Model manifest does not match the pinned toxicity model revision.")

    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("Model manifest has no file checksums.")

    for filename, expected_digest in files.items():
        artifact_path = model_dir / filename
        if not artifact_path.is_file():
            raise FileNotFoundError(f"Model artifact file is missing: {artifact_path}")
        if _sha256(artifact_path) != expected_digest:
            raise ValueError(f"Checksum validation failed for model artifact {artifact_path}.")

    return manifest


def _resolve_device(device_name: str) -> torch.device:
    if device_name == "auto":
        if torch.backends.mps.is_available():
            return torch.device("mps")
        if torch.cuda.is_available():
            return torch.device("cuda")
        return torch.device("cpu")
    return torch.device(device_name)


class ToxicityClassifier:
    """Load and run the actual multi-label toxicity classifier from disk."""

    def __init__(self, model_dir: Path, device: str = "auto") -> None:
        manifest = verify_model_artifact(model_dir)
        self._device = _resolve_device(device)
        self._tokenizer = AutoTokenizer.from_pretrained(  # type: ignore[no-untyped-call]
            model_dir,
            local_files_only=True,
            use_fast=True,
        )
        self._model = AutoModelForSequenceClassification.from_pretrained(
            model_dir,
            local_files_only=True,
            use_safetensors=True,
        )
        self._model.to(self._device)
        self._model.eval()

        labels = {
            int(index): str(label).strip().lower()
            for index, label in self._model.config.id2label.items()
        }
        matching_labels = [index for index, label in labels.items() if label == "toxic"]
        if len(matching_labels) != 1:
            raise ValueError(f"Expected one `toxic` output label, found {labels!r}.")
        self._toxic_index = matching_labels[0]
        self.model_version = f"{manifest['model_id']}@{manifest['revision']}"

    def score(self, text: str) -> ToxicityScore:
        """Return the sigmoid probability for the model's `toxic` label."""

        encoded = self._tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=MAX_TOKEN_LENGTH,
        )
        encoded = {name: tensor.to(self._device) for name, tensor in encoded.items()}
        with torch.inference_mode():
            logits = self._model(**encoded).logits[0]
            score = float(torch.sigmoid(logits[self._toxic_index]).cpu().item())
        if not 0.0 <= score <= 1.0:
            raise RuntimeError("Toxicity model returned a score outside [0, 1].")
        return ToxicityScore(score=score, model_version=self.model_version)

    def warm_up(self) -> None:
        """Run a real inference before the API marks itself ready."""

        self.score("This is a neutral sentence used to warm up the classifier.")


def load_toxicity_classifier(model_dir: Path, device: str) -> ToxicityClassifier:
    """Load local model files; this function never downloads model artifacts."""

    classifier = ToxicityClassifier(model_dir=model_dir, device=device)
    classifier.warm_up()
    return classifier
