"""Build the verified ONNX cache for the pinned models inside a deployable image."""

from pathlib import Path

from guardrail_mini.models.onnx_runtime import load_onnx_text_classifier
from guardrail_mini.policies.prompt_injection import (
    MAX_TOKEN_LENGTH as PROMPT_MAX_TOKEN_LENGTH,
)
from guardrail_mini.policies.prompt_injection import MODEL_ID as PROMPT_MODEL_ID
from guardrail_mini.policies.prompt_injection import MODEL_REVISION as PROMPT_MODEL_REVISION
from guardrail_mini.policies.toxicity import MAX_TOKEN_LENGTH as TOXICITY_MAX_TOKEN_LENGTH
from guardrail_mini.policies.toxicity import MODEL_ID as TOXICITY_MODEL_ID
from guardrail_mini.policies.toxicity import MODEL_REVISION as TOXICITY_MODEL_REVISION


def main() -> None:
    """Export both pinned classifiers before creating the runtime image."""

    cache_dir = Path("data/onnx-cache")
    toxicity = load_onnx_text_classifier(
        Path("models/toxicity/v1"),
        cache_dir,
        TOXICITY_MODEL_ID,
        TOXICITY_MODEL_REVISION,
        "toxic",
        "sigmoid",
        TOXICITY_MAX_TOKEN_LENGTH,
        "cpu",
    )
    toxicity.warm_up()

    prompt_injection = load_onnx_text_classifier(
        Path("models/prompt-injection/v1"),
        cache_dir,
        PROMPT_MODEL_ID,
        PROMPT_MODEL_REVISION,
        "injection",
        "softmax",
        PROMPT_MAX_TOKEN_LENGTH,
        "cpu",
    )
    prompt_injection.warm_up()
    print(f"Prepared ONNX model caches in {cache_dir}.")


if __name__ == "__main__":
    main()
