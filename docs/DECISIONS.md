# Decision Log

## Initial API and package structure

- **Problem:** Start with a runnable service while keeping HTTP, configuration, and future policy/model code easy to evolve independently.
- **Options:** A single script; a framework such as FastAPI; a larger service framework.
- **Decision:** Use a `src/` Python package and FastAPI application factory.
- **Reason:** FastAPI provides typed request handling and generated OpenAPI documentation with little setup. The application factory makes configuration and tests straightforward.
- **Trade-off:** The service has a few more files than a single script.
- **Reconsider when:** The API surface or deployment model makes a different framework materially simpler.

## Python runtime

- **Problem:** Select a local Python version compatible with current ML libraries.
- **Options:** Python 3.12 or the installed Python 3.14.
- **Decision:** Recommend Python 3.12 for development and target Python 3.11 through 3.14 in package metadata.
- **Reason:** Python 3.12 is available locally and is a conservative target for ML package wheels.
- **Trade-off:** The newest Python runtime is not the recommended environment.
- **Reconsider when:** The selected model runtime and all dependencies publish stable wheels for newer Python versions.

## First policy implementation

- **Problem:** Establish a real policy end-to-end before expanding the policy engine.
- **Options:** Start with toxicity, PII, or prompt-injection detection.
- **Decision:** Start with [`unitary/toxic-bert`](https://huggingface.co/unitary/toxic-bert) in Phase 2 and use its `toxic` output as the policy score.
- **Reason:** The Hugging Face model card documents a BERT multi-label toxicity classifier, lists an Apache-2.0 license, and provides local Transformers usage. It is a concrete real-model path with no paid API.
- **Trade-off:** The weights are about 438 MB and the model has about 0.1B parameters, so startup and memory use need to be measured. The model card also warns that its Hugging Face version can differ from Detoxify outputs and notes potential bias around profanity and identity terms.
- **Reconsider when:** Local profiling or evaluation shows a maintained smaller model provides a better measured accuracy/latency trade-off. The model card's source and limitations are recorded in the docs before this decision is used for a public demo.

## Initial model-serving shape

- **Problem:** Decide whether to require one shared encoder before any policy can work.
- **Options:** Force all first policies into a shared encoder, or implement policy-specific approaches first.
- **Decision:** Begin with working policy-specific implementations and revisit shared representations after profiling and evaluation.
- **Reason:** Toxicity, PII, and prompt-injection detection may use different techniques; an early shared model could add complexity without measured benefit.
- **Trade-off:** The initial policies may load separate artifacts.
- **Reconsider when:** Measured model memory or latency shows a shared encoder would help and compatible training/model artifacts are available.
