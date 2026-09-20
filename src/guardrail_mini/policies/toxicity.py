"""Local toxicity classifier backed by a pinned Hugging Face artifact."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from guardrail_mini.core.policy_engine import PolicyAction, PolicyMetadata, PolicyResult
from guardrail_mini.models.artifacts import verify_model_artifact as verify_artifact

MODEL_ID = "unitary/toxic-bert"
MODEL_REVISION = "4d6c22e74ba2fdd26bc4f7238f50766b045a0d94"
MAX_TOKEN_LENGTH = 512


@dataclass(frozen=True)
class ToxicityScore:
    """The classifier's normalized toxicity score and artifact version."""

    score: float
    model_version: str


class ToxicityScorer(Protocol):
    """Minimal interface required by the toxicity policy."""

    def score(self, text: str) -> ToxicityScore: ...


def verify_model_artifact(model_dir: Path) -> dict[str, object]:
    """Validate the local toxicity artifact before the tokenizer or model is loaded."""

    return verify_artifact(model_dir, MODEL_ID, MODEL_REVISION)


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
        self._tokenizer = AutoTokenizer.from_pretrained(
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


class ToxicityPolicy:
    """Turn a classifier score into an explicit ALLOW, REVIEW, or BLOCK result."""

    def __init__(
        self,
        classifier: ToxicityScorer,
        threshold: float,
        review_threshold: float | None,
    ) -> None:
        if review_threshold is not None and review_threshold > threshold:
            raise ValueError("The review threshold must not exceed the block threshold.")
        self._classifier = classifier
        self._threshold = threshold
        self._review_threshold = review_threshold
        self.metadata = PolicyMetadata(
            id="toxicity",
            name="Toxicity detection",
            version="1",
            threshold=threshold,
            review_threshold=review_threshold,
            severity=3,
        )

    def evaluate(self, text: str) -> PolicyResult:
        prediction = self._classifier.score(text)
        if prediction.score >= self._threshold:
            action = PolicyAction.BLOCK
        elif self._review_threshold is not None and prediction.score >= self._review_threshold:
            action = PolicyAction.REVIEW
        else:
            action = PolicyAction.ALLOW
        return PolicyResult(
            policy_id=self.metadata.id,
            score=prediction.score,
            threshold=self._threshold,
            action=action,
            model_version=prediction.model_version,
            severity=self.metadata.severity,
        )
