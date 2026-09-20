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

### Prerequisite checklist for Phases 1–3

- [x] Python 3.12 runtime available.
- [x] Project-local virtual environment created at `.venv/`.
- [x] Runtime and development dependencies installed in `.venv/`.
- [x] Isolated Git repository created in the project directory.
- [x] Install the Phase 2 ML dependencies in `.venv/`.
- [x] Pin the model revision and verify its public license metadata before downloading it.
- [x] Download the selected model artifact and write its checksum manifest.

Docker, PostgreSQL, and MinIO are not prerequisites for Phases 1–3. Docker Desktop must be started before the later container-based infrastructure phases.

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

## Next

Phase 4 adds PII detection and prompt-injection detection as independent policy implementations. PII will combine deterministic entity patterns with a local NER model; prompt injection will use a dedicated open model classifier after its source and license are checked.
