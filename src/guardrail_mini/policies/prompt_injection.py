"""Prompt-injection classifier and policy backed by a pinned local model."""

from pathlib import Path
from time import perf_counter
from typing import Protocol

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from guardrail_mini.core.policy_engine import PolicyAction, PolicyMetadata, PolicyResult
from guardrail_mini.models.artifacts import verify_model_artifact
from guardrail_mini.observability.metrics import MODEL_INFERENCE_LATENCY_SECONDS

MODEL_ID = "patronus-studio/wolf-defender-prompt-injection-small"
MODEL_REVISION = "cdcdf7d0231d68f39cc3bb1b70f6a2bdfca8ad55"
MAX_TOKEN_LENGTH = 2048


class PromptInjectionRuntime(Protocol):
    """A loaded prompt-injection scorer that supports startup warm-up."""

    model_version: str

    def score(self, text: str) -> float: ...

    def warm_up(self) -> None: ...


class PromptInjectionClassifier:
    """Load and run the pinned multilingual prompt-injection classifier."""

    def __init__(self, model_dir: Path, device: str = "auto") -> None:
        manifest = verify_model_artifact(model_dir, MODEL_ID, MODEL_REVISION)
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
        matching_labels = [index for index, label in labels.items() if label == "injection"]
        if len(matching_labels) != 1:
            raise ValueError(f"Expected one `INJECTION` output label, found {labels!r}.")
        self._injection_index = matching_labels[0]
        self.model_version = f"{manifest['model_id']}@{manifest['revision']}"

    def score(self, text: str) -> float:
        """Return the softmax probability for the `INJECTION` class."""

        encoded = self._tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=MAX_TOKEN_LENGTH,
        )
        encoded = {name: tensor.to(self._device) for name, tensor in encoded.items()}
        with torch.inference_mode():
            logits = self._model(**encoded).logits
            score = float(torch.softmax(logits, dim=-1)[0, self._injection_index].cpu().item())
        if not 0.0 <= score <= 1.0:
            raise RuntimeError("Prompt-injection model returned a score outside [0, 1].")
        return score

    def warm_up(self) -> None:
        self.score("A neutral request asking for a summary of a public document.")


def _resolve_device(device_name: str) -> torch.device:
    if device_name == "auto":
        if torch.backends.mps.is_available():
            return torch.device("mps")
        if torch.cuda.is_available():
            return torch.device("cuda")
        return torch.device("cpu")
    return torch.device(device_name)


class PromptInjectionPolicy:
    """Convert classifier probability into review or block actions."""

    def __init__(
        self,
        classifier: PromptInjectionRuntime,
        threshold: float,
        review_threshold: float | None,
    ) -> None:
        if review_threshold is not None and review_threshold > threshold:
            raise ValueError(
                "The prompt-injection review threshold must not exceed its block threshold."
            )
        self._classifier = classifier
        self._threshold = threshold
        self._review_threshold = review_threshold
        self.metadata = PolicyMetadata(
            id="prompt_injection",
            name="Prompt-injection detection",
            version="1",
            threshold=threshold,
            review_threshold=review_threshold,
            severity=3,
        )

    def evaluate(self, text: str) -> PolicyResult:
        started = perf_counter()
        try:
            score = self._classifier.score(text)
        finally:
            MODEL_INFERENCE_LATENCY_SECONDS.labels(policy_id=self.metadata.id).observe(
                perf_counter() - started
            )
        if score >= self._threshold:
            action = PolicyAction.BLOCK
        elif self._review_threshold is not None and score >= self._review_threshold:
            action = PolicyAction.REVIEW
        else:
            action = PolicyAction.ALLOW
        return PolicyResult(
            policy_id=self.metadata.id,
            score=score,
            threshold=self._threshold,
            action=action,
            model_version=self._classifier.model_version,
            severity=self.metadata.severity,
        )


def load_prompt_injection_classifier(
    model_dir: Path,
    device: str,
    runtime: str = "pytorch",
    onnx_cache_dir: Path = Path("data/onnx-cache"),
) -> PromptInjectionRuntime:
    if runtime == "onnxruntime":
        from guardrail_mini.models.onnx_runtime import load_onnx_text_classifier

        onnx_classifier = load_onnx_text_classifier(
            model_dir,
            onnx_cache_dir,
            MODEL_ID,
            MODEL_REVISION,
            "injection",
            "softmax",
            MAX_TOKEN_LENGTH,
            device,
        )
        onnx_classifier.warm_up()
        return onnx_classifier
    if runtime != "pytorch":
        raise ValueError(f"Unsupported model runtime: {runtime!r}.")

    classifier = PromptInjectionClassifier(model_dir=model_dir, device=device)
    classifier.warm_up()
    return classifier
