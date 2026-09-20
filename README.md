# Guardrail Mini

A portfolio project for a small, production-minded guardrail API. It evaluates text with specialized policy implementations and returns `ALLOW`, `BLOCK`, or `REVIEW` decisions.

The current implementation is **Phase 3: modular policy evaluation**. It includes a local toxicity classifier, request-selected policies, `ANY_BLOCK` aggregation, an in-memory policy catalog, and readiness-gated API. PII and prompt-injection policies, authentication, persistence, observability, and deployment are later phases and are not implemented yet.

See [the phase status and environment checklist](docs/PHASE_STATUS.md), [the architecture overview](docs/architecture/system-overview.md), and [the decision log](docs/DECISIONS.md).

## Requirements

- Python 3.11 or newer, below 3.15. Python 3.12 is the recommended local runtime for ML package compatibility.
- Git.
- Docker Desktop is optional now and will be used for the later local database, artifact store, monitoring, and application stack.

No global Python packages are required. All Python packages install inside a project virtual environment. The model weights are about 438 MB and are downloaded once into the ignored `models/` directory.

## Local setup

Run these commands from the repository root.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev,ml]"
cp .env.example .env
python scripts/download_model.py
python -m guardrail_mini
```

On Windows PowerShell, activate the environment with `.venv\Scripts\Activate.ps1`. On Windows Command Prompt, use `.venv\Scripts\activate.bat`. If Python 3.12 is not available, install Python 3.12 or use another supported version with the matching `python` command.

The model download checks the pinned Hugging Face revision and Apache-2.0 metadata, then writes SHA-256 checksums into `models/toxicity/v1/manifest.json`. The API loads only these local files, verifies every checksum, and performs a warm-up inference before reporting ready. It never downloads a model during a request.

Expected startup output includes `Uvicorn running on http://127.0.0.1:8000` after the model has loaded and warmed up. On Apple Silicon, `GUARDRAIL_MODEL_DEVICE=auto` uses Metal (MPS) when available; otherwise it uses CPU. Set `GUARDRAIL_MODEL_DEVICE=cpu` in `.env` to force CPU inference.

## Check the API

With the server running, open <http://127.0.0.1:8000/docs> for Swagger UI or run:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/live
curl http://127.0.0.1:8000/ready
curl -X POST http://127.0.0.1:8000/v1/guardrails/evaluate \
  -H 'Content-Type: application/json' \
  -d '{"input":"You are kind and helpful."}'
```

The evaluate response includes a score in `[0, 1]` per policy, configured thresholds, a combined `ALLOW`, `REVIEW`, or `BLOCK` action, model revisions, a request ID, and latency. By default the block threshold is `0.80` and the review threshold is `0.55`; set `GUARDRAIL_TOXICITY_THRESHOLD` or `GUARDRAIL_TOXICITY_REVIEW_THRESHOLD` in `.env` to change them. Policies default to `toxicity` and can be selected with `"policies": ["toxicity"]`. The catalog is available at `/v1/policies`. The automatic tests run with:

```bash
pytest
```

## Project map

```text
src/guardrail_mini/     application, API, and policy/model code
scripts/                model artifact setup scripts
tests/                  automated tests
docs/architecture/      architecture and request-flow notes
docs/DECISIONS.md       major implementation choices
```

## Planned implementation

Later phases add a modular policy engine, PII and prompt-injection checks, PostgreSQL, API-key authentication, MinIO model artifact storage, observability, Docker, load testing, CI, and a public deployment. This README will be updated as each phase is implemented and verified.
