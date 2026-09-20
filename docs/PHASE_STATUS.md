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
- [ ] Install the Phase 2 ML dependencies in `.venv/`.
- [ ] Allow access to Hugging Face to download the selected model artifact before running Phase 2 inference.

Docker, PostgreSQL, and MinIO are not prerequisites for Phases 1–3. Docker Desktop must be started before the later container-based infrastructure phases.

## Phase 1 — Architecture and skeleton

**Status: complete.** The FastAPI application factory, validated settings, health routes, smoke test, README setup steps, architecture overview, inference path, model-serving plan, and initial decision log are present. Swagger/OpenAPI is served by FastAPI.

Verification on Python 3.12.10:

- `pytest`: 1 passed.
- `ruff check .`: passed.
- `ruff format --check .`: passed.
- `mypy src tests`: passed.
- Local Uvicorn startup: `/health`, `/live`, `/ready`, and `/openapi.json` returned HTTP 200.

## Next

Phase 2 will add one real toxicity classifier, load it before serving requests, and expose its score, threshold, and decision through an inference endpoint.
