"""Local ONNX Runtime backend for the pinned sequence classifiers."""

import gc
import hashlib
import json
import math
import os
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Literal, cast
from uuid import uuid4

import numpy as np
import onnx
import onnxruntime as ort
import onnxscript
import torch
from torch.export import Dim
from transformers import AutoConfig, AutoModelForSequenceClassification, AutoTokenizer

from guardrail_mini.models.artifacts import verify_model_artifact

ScoreMode = Literal["sigmoid", "softmax"]


class _LogitsModel(torch.nn.Module):
    """Expose only model logits to the ONNX exporter."""

    def __init__(self, model: torch.nn.Module) -> None:
        super().__init__()
        self.model = model

    def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
        return cast(
            torch.Tensor,
            self.model(input_ids=input_ids, attention_mask=attention_mask).logits,
        )


class OnnxTextClassifier:
    """Score text using a cached float32 ONNX graph on the CPU provider."""

    def __init__(
        self,
        session: ort.InferenceSession,
        tokenize: Callable[[str], Mapping[str, np.ndarray]],
        model_version: str,
        class_index: int,
        score_mode: ScoreMode,
    ) -> None:
        self._session = session
        self._tokenize = tokenize
        self._class_index = class_index
        self._score_mode = score_mode
        self.model_version = model_version

    def score(self, text: str) -> float:
        encoded = self._tokenize(text)
        logits = self._session.run(
            ["logits"],
            {
                "input_ids": encoded["input_ids"],
                "attention_mask": encoded["attention_mask"],
            },
        )[0][0]
        values = np.asarray(logits, dtype=np.float64)
        if self._score_mode == "sigmoid":
            value = float(values[self._class_index])
            if value >= 0:
                return 1 / (1 + math.exp(-value))
            exp_value = math.exp(value)
            return exp_value / (1 + exp_value)

        shifted = values - values.max()
        probabilities = np.exp(shifted) / np.exp(shifted).sum()
        return float(probabilities[self._class_index])

    def warm_up(self) -> None:
        self.score("A neutral request used to warm the local classifier.")


def load_onnx_text_classifier(
    model_dir: Path,
    cache_dir: Path,
    model_id: str,
    revision: str,
    label_name: str,
    score_mode: ScoreMode,
    max_token_length: int,
    device: str,
) -> OnnxTextClassifier:
    """Verify, export if needed, then load the model through ONNX Runtime."""

    if device not in {"auto", "cpu"}:
        raise ValueError("The ONNX Runtime backend currently supports CPU inference only.")
    manifest = verify_model_artifact(model_dir, model_id, revision)
    manifest_digest = hashlib.sha256((model_dir / "manifest.json").read_bytes()).hexdigest()
    runtime_identity = hashlib.sha256(
        f"{manifest_digest}:{torch.__version__}:{onnx.__version__}:"
        f"{onnxscript.__version__}:{ort.__version__}:dynamo-opset18".encode()
    ).hexdigest()[:16]
    graph_dir = cache_dir / model_id.replace("/", "--") / revision / runtime_identity
    graph_dir.mkdir(parents=True, exist_ok=True)
    graph_path = graph_dir / "model.onnx"
    metadata_path = graph_dir / "export.json"
    config = AutoConfig.from_pretrained(model_dir, local_files_only=True)
    labels = {int(index): str(label).strip().lower() for index, label in config.id2label.items()}
    matching_labels = [index for index, label in labels.items() if label == label_name]
    if len(matching_labels) != 1:
        raise ValueError(f"Expected one {label_name!r} classifier output, found {labels!r}.")
    class_index = matching_labels[0]

    tokenizer = AutoTokenizer.from_pretrained(
        model_dir,
        local_files_only=True,
        use_fast=True,
    )

    def tokenize(text: str) -> Mapping[str, np.ndarray]:
        encoded = tokenizer(
            text,
            return_tensors="np",
            truncation=True,
            max_length=max_token_length,
        )
        return cast(Mapping[str, np.ndarray], encoded)

    model_version = f"{manifest['model_id']}@{manifest['revision']}"
    if not graph_path.is_file() or not metadata_path.is_file():
        model = AutoModelForSequenceClassification.from_pretrained(
            model_dir,
            local_files_only=True,
            use_safetensors=True,
        )
        model.to("cpu")
        model.eval()
        sample = tokenizer(
            "A neutral request used to trace the dynamic classifier graph.",
            return_tensors="pt",
            truncation=True,
            max_length=max_token_length,
        )
        batch_dimension = Dim("batch", min=1, max=32)
        sequence_dimension = Dim("sequence", min=2, max=max_token_length)
        export_model = _LogitsModel(model).eval()
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix="model-", suffix=".onnx", dir=graph_dir
        )
        os.close(file_descriptor)
        temporary_graph = Path(temporary_name)
        temporary_metadata = graph_dir / f"export-{uuid4().hex}.json.tmp"
        try:
            torch.onnx.export(
                export_model,
                (sample["input_ids"], sample["attention_mask"]),
                str(temporary_graph),
                input_names=["input_ids", "attention_mask"],
                output_names=["logits"],
                dynamic_shapes=(
                    {0: batch_dimension, 1: sequence_dimension},
                    {0: batch_dimension, 1: sequence_dimension},
                ),
                opset_version=18,
                dynamo=True,
                external_data=False,
            )
            onnx.checker.check_model(str(temporary_graph))
            os.replace(temporary_graph, graph_path)
            metadata = {
                "model_id": model_id,
                "revision": revision,
                "source_manifest_sha256": manifest_digest,
                "torch_version": torch.__version__,
                "onnx_version": onnx.__version__,
                "onnxscript_version": onnxscript.__version__,
                "onnxruntime_version": ort.__version__,
                "exporter": "torch.onnx.export(dynamo=True)",
                "opset": 18,
                "score_mode": score_mode,
                "label": label_name,
            }
            temporary_metadata.write_text(json.dumps(metadata, indent=2) + "\n")
            os.replace(temporary_metadata, metadata_path)
        finally:
            temporary_graph.unlink(missing_ok=True)
            temporary_metadata.unlink(missing_ok=True)
            del model
        gc.collect()

    options = ort.SessionOptions()
    options.intra_op_num_threads = torch.get_num_threads()
    options.inter_op_num_threads = 1
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    session = ort.InferenceSession(
        str(graph_path),
        sess_options=options,
        providers=["CPUExecutionProvider"],
    )
    return OnnxTextClassifier(
        session,
        tokenize,
        model_version,
        class_index,
        score_mode,
    )
