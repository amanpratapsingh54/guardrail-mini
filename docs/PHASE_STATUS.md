# Phase Status

## Phase 0 — Environment inspection

Inspected on 2026-09-19 before creating the application files.

| Item | Finding |
| --- | --- |
| OS and architecture | macOS 26.0, Apple Silicon (`arm64`) |
| Hardware | Apple M5 Pro, 16-core integrated GPU; Metal is available |
| Memory | `sysctl hw.memsize` was blocked by the environment, so the total RAM is not recorded |
| Python | Python 3.12.10 and 3.14.7 are installed; Python 3.12 is the project runtime |
| Git | Git 2.54.0 is installed; a project-local repository was initialized to avoid the unrelated home-level Git repository |
| Docker | Docker CLI 29.4.3 is installed; the Docker daemon was not running during inspection |
| `uv` | Not installed; not required because the project uses Python's built-in `venv` and pip |
| Initial repository | Empty |

### Prerequisite checklist for Phases 1–4

- [x] Python 3.12 runtime available.
- [x] Project-local virtual environment created at `.venv/`.
- [x] Runtime and development dependencies installed in `.venv/`.
- [x] Isolated Git repository created in the project directory.
- [x] Install runtime, ML, PII, and development dependencies in `.venv/`.
- [x] Install spaCy's English small model (`en_core_web_sm` 3.8.0).
- [x] Pin both Hugging Face model revisions and verify their public Apache-2.0 metadata.
- [x] Download both Transformer artifacts and write their checksum manifests.

Docker, PostgreSQL, and MinIO are not prerequisites for Phases 1–4. Docker Desktop must be started before the later container-based infrastructure phases.

Although macOS reports Metal support, the installed PyTorch 2.14.0 runtime reports `torch.backends.mps.is_available() == False`; local inference currently uses CPU. The implementation selects MPS only when PyTorch confirms it is available.

## Phase 1 — Architecture and skeleton

**Status: complete.** The FastAPI application factory, validated settings, health routes, smoke test, README setup steps, architecture overview, inference path, model-serving plan, and initial decision log are present. Swagger/OpenAPI is served by FastAPI.

Verification on Python 3.12.10:

- `pytest`: 1 passed.
- `ruff check .`: passed.
- `ruff format --check .`: passed.
- `mypy src tests`: passed.
- Local Uvicorn startup: `/health`, `/live`, `/ready`, and `/openapi.json` returned HTTP 200.

## Phase 2 — First real policy

**Status: complete.** The API has a toxicity evaluation endpoint. Startup loads the pinned local model, verifies its manifest checksums, and warms it up before readiness. The model artifact is present locally under the ignored `models/` directory. Real inference tests verified that a benign example returns `ALLOW` and a hostile example returns `BLOCK` at the configured `0.80` threshold.

Model: [`unitary/toxic-bert`](https://huggingface.co/unitary/toxic-bert/tree/4d6c22e74ba2fdd26bc4f7238f50766b045a0d94), Apache-2.0, revision `4d6c22e74ba2fdd26bc4f7238f50766b045a0d94`.

Verification on Python 3.12.10:

- `pytest`: 3 passed, including real local model inference through the API.
- `ruff check .` and `ruff format --check .`: passed.
- `mypy src tests scripts`: passed.
- Pinned model manifest validation: passed.

## Phase 3 — Policy engine

**Status: complete.** Policy metadata and implementations are separated behind a registry. Requests can select policies, policy metadata is available through `/v1/policies`, `ANY_BLOCK` aggregation is the default, and `HIGHEST_SEVERITY` is present as a tested extension strategy. The toxicity policy supports `ALLOW`, `REVIEW`, and `BLOCK` thresholds. Unknown policy IDs return the documented structured error.

Verification:

- `pytest`: 15 passed, including real toxicity model inference, threshold decisions, aggregation, and settings validation.
- `ruff check .` and `ruff format --check .`: passed.
- `mypy src tests scripts`: passed.
- Live API checks: policy list/detail and safe-text evaluation returned HTTP 200; an unknown policy returned HTTP 404 with `POLICY_NOT_FOUND` and a request ID.

## Phase 4 — Additional guardrails

**Status: complete.** Added a local hybrid PII policy using Presidio patterns plus spaCy person/location NER, and a local prompt-injection classifier. Policy selection and aggregation now work across all three policies. PII responses expose entity categories but never matched values. Startup verifies both Transformer artifact manifests, initializes the local NLP pipeline, warms all three implementations, and marks readiness only after they succeed.

Models and components:

- Toxicity: [`unitary/toxic-bert`](https://huggingface.co/unitary/toxic-bert/tree/4d6c22e74ba2fdd26bc4f7238f50766b045a0d94), Apache-2.0, pinned revision recorded in `models/toxicity/v1/manifest.json`.
- Prompt injection: [`patronus-studio/wolf-defender-prompt-injection-small`](https://huggingface.co/patronus-studio/wolf-defender-prompt-injection-small/tree/cdcdf7d0231d68f39cc3bb1b70f6a2bdfca8ad55), Apache-2.0, pinned revision `cdcdf7d0231d68f39cc3bb1b70f6a2bdfca8ad55`.
- PII: Presidio Analyzer 2.2.364 (MIT) and spaCy `en_core_web_sm` 3.8.0 (MIT).

The two Transformer weight files occupy about 955 MB together. Current checks use CPU because PyTorch reports MPS unavailable in this environment. The prompt model's current policy input is truncated at 2,048 tokens; its English and German results are strongest, and it remains one layer rather than a standalone security boundary.

Verification on Python 3.12.10:

- `pytest`: 15 passed, including real toxicity, PII, and prompt-injection inference through the API.
- `ruff check .` and `ruff format --check .`: passed.
- `mypy src tests scripts`: passed.
- PII smoke samples: benign text returned `ALLOW`; text with a name, email, and phone returned `BLOCK` with entity types only.
- Prompt-injection smoke samples: benign request scored `0.0001`; an instruction override scored `0.9998` and returned `BLOCK`.
- Live `python -m guardrail_mini` check: `/health`, `/ready`, and `/v1/policies` returned HTTP 200; live PII and prompt-injection evaluation returned HTTP 200 with `BLOCK` and no PII values in the response.

## Next

Phase 5 adds PostgreSQL control-plane persistence with SQLAlchemy, Alembic migrations, model and policy metadata, and API-key/project tables.
