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
- **Decision:** Use [`unitary/toxic-bert`](https://huggingface.co/unitary/toxic-bert/tree/4d6c22e74ba2fdd26bc4f7238f50766b045a0d94) at immutable revision `4d6c22e74ba2fdd26bc4f7238f50766b045a0d94` and use its `toxic` sigmoid output as the policy score.
- **Reason:** The Hugging Face model card documents a BERT multi-label toxicity classifier, lists an Apache-2.0 license, and provides local Transformers usage. The downloader verifies the selected revision and license before saving files locally.
- **Trade-off:** The weights are about 438 MB and the model has about 0.1B parameters, so startup and memory use need to be measured. The model card also warns that its Hugging Face version can differ from Detoxify outputs and notes potential bias around profanity and identity terms.
- **Reconsider when:** Local profiling or evaluation shows a maintained smaller model provides a better measured accuracy/latency trade-off. The model card's source and limitations are recorded in the docs before this decision is used for a public demo.

## Initial model-serving shape

- **Problem:** Decide whether to require one shared encoder before any policy can work.
- **Options:** Force all first policies into a shared encoder, or implement policy-specific approaches first.
- **Decision:** Begin with working policy-specific implementations and revisit shared representations after profiling and evaluation.
- **Reason:** Toxicity, PII, and prompt-injection detection may use different techniques; an early shared model could add complexity without measured benefit.
- **Trade-off:** The initial policies may load separate artifacts.
- **Reconsider when:** Measured model memory or latency shows a shared encoder would help and compatible training/model artifacts are available.

## Policy interface and aggregation

- **Problem:** Let callers select policy checks while keeping their implementations independent and combining results predictably.
- **Options:** Hard-code the toxicity check in the route, or resolve policy implementations through a registry and aggregate typed results.
- **Decision:** Use a registry behind a policy interface. Start with `ANY_BLOCK` and include `HIGHEST_SEVERITY` as an explicit extension strategy. A score at or above the review threshold returns `REVIEW`; a score at or above the block threshold returns `BLOCK`.
- **Reason:** This keeps model inference separate from policy thresholds and makes new checks selectable without growing route-specific conditionals.
- **Trade-off:** There is some extra abstraction for a one-policy service; the registry is intentionally in-process until PostgreSQL is added.
- **Reconsider when:** Policy configuration is tenant-specific or the number of implementations requires a plugin lifecycle.

## PII detection

- **Problem:** Detect both structured identifiers and free-text personal entities without sending text to an external service.
- **Options:** Write a small set of regular expressions, use a large Transformer NER model, or combine local pattern recognizers with a compact NER pipeline.
- **Decision:** Use Microsoft Presidio's MIT-licensed recognizer engine with local email, phone, US SSN, credit-card, IP, and spaCy NER recognizers. Use the MIT-licensed `en_core_web_sm` 3.8.0 model for English person and location entities.
- **Reason:** Presidio supplies validated identifier recognizers; the small spaCy model adds person and place extraction without another large Transformer model. The API returns entity category names and scores but never the detected values. The email recognizer uses a local pattern instead of Presidio's default URL-dependent validator so startup does not fetch a public suffix list.
- **Trade-off:** Named-entity coverage is English-focused, and SSN recognition is US-specific. The local email pattern does not validate domain registration. Recognizers still have false positives and false negatives.
- **Reconsider when:** Multilingual coverage or measured recall justifies another model, a custom entity set, or per-tenant PII rules.

## Prompt-injection detection

- **Problem:** Detect malicious prompt instructions using a local specialist classifier.
- **Options:** Use a pattern-only check, an older base DeBERTa model, or a compact current classifier trained specifically for prompt injections and jailbreak-like instructions.
- **Decision:** Use [`patronus-studio/wolf-defender-prompt-injection-small`](https://huggingface.co/patronus-studio/wolf-defender-prompt-injection-small/tree/cdcdf7d0231d68f39cc3bb1b70f6a2bdfca8ad55) at pinned revision `cdcdf7d0231d68f39cc3bb1b70f6a2bdfca8ad55`, Apache-2.0. Use Transformers 5.10+ because the model's tokenizer metadata uses the TokenizersBackend API.
- **Reason:** The model card describes a compact 0.1B-parameter binary classifier, a 2,048-token context window, and on-device use. The Hugging Face revision is pinned and the downloaded files are checksummed.
- **Trade-off:** The weight file is about 537 MB, adding startup time and memory. The current implementation truncates to 2,048 tokens; the model card warns no classifier catches every attack and that English/German are the best-evaluated languages. Published benchmark numbers are model-author results, not project measurements.
- **Reconsider when:** Local evaluation or profiling shows a smaller maintained model or the included ONNX quantized artifact improves the quality/latency trade-off. ONNX remains for the later profile-first optimization phase.

## PostgreSQL control plane

- **Problem:** Persist project ownership, API-key state, policy defaults/overrides, and model artifact metadata without putting a database query in every inference step.
- **Options:** Keep all metadata in process settings, use a document store, or use PostgreSQL with SQLAlchemy and explicit migrations.
- **Decision:** Use PostgreSQL 16, SQLAlchemy 2, Alembic, and the Psycopg 3 driver. Separate global policy metadata from project-specific threshold and enablement overrides; store only API-key hashes and metadata, never raw key material.
- **Reason:** PostgreSQL provides relational constraints for tenant/project ownership, unique credentials, policy references, and model version identity. Alembic keeps schema changes reviewable and reproducible. The synchronous session API fits the current synchronous model inference routes.
- **Trade-off:** A PostgreSQL service is an additional local dependency. The current inference registry remains cached in process; database-backed API-key authentication and startup metadata loading are wired in subsequent phases.
- **Reconsider when:** Measured control-plane access or operational requirements call for async database access or a separate configuration service.
