# Guardrail Mini

A portfolio project for a small, production-minded guardrail API. It will evaluate text with specialized policy implementations and return `ALLOW`, `BLOCK`, or `REVIEW` decisions.

The project is being built in phases. The current implementation is **Phase 1: API skeleton**. It provides validated configuration, FastAPI's generated OpenAPI docs, and health, liveness, and readiness endpoints. Policy inference, authentication, persistence, and deployment are planned phases and are not implemented yet.

See [the Phase 0/1 status and environment checklist](docs/PHASE_STATUS.md) and [the architecture overview](docs/architecture/system-overview.md).

## Requirements

- Python 3.11 or newer, below 3.15. Python 3.12 is the recommended local runtime for ML package compatibility.
- Git.
- Docker Desktop is optional for Phase 1 and will be used for the later local infrastructure stack.

No global Python packages are required. All Python packages install inside a project virtual environment.

## Local setup

Run these commands from the repository root.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
cp .env.example .env
python -m guardrail_mini
```

On Windows PowerShell, activate the environment with `.venv\Scripts\Activate.ps1`. On Windows Command Prompt, use `.venv\Scripts\activate.bat`. If Python 3.12 is not available, install Python 3.12 or use another supported version with the matching `python` command.

Expected startup output includes `Uvicorn running on http://127.0.0.1:8000`.

## Check the API

With the server running, open <http://127.0.0.1:8000/docs> for Swagger UI or run:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/live
curl http://127.0.0.1:8000/ready
```

Each endpoint returns a JSON status. The automatic smoke tests run with:

```bash
pytest
```

## Project map

```text
src/guardrail_mini/     application and API code
tests/                  automated tests
docs/architecture/      architecture and request-flow notes
docs/DECISIONS.md       major implementation choices
```

## Planned implementation

The next phase adds a real toxicity classifier and an end-to-end score and threshold decision. Later phases add the policy engine and PII and prompt-injection checks, followed by PostgreSQL, API-key authentication, model artifact storage, observability, Docker, load testing, CI, and a public deployment. This README will be updated as each phase is implemented and verified.
