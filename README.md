# Guardrail Mini

A portfolio project for a small, production-minded guardrail API. It evaluates text with specialized policy implementations and returns `ALLOW`, `BLOCK`, or `REVIEW` decisions.

The current implementation is **Phase 5: three local guardrail policies and a PostgreSQL control-plane schema**. It includes toxicity classification, hybrid PII detection, prompt-injection classification, request-selected policies, `ANY_BLOCK` aggregation, SQLAlchemy records for tenants, projects, policy configuration, API keys, and model versions, plus an Alembic migration. API-key enforcement, MinIO, observability, and deployment are later phases.

See [the phase status and environment checklist](docs/PHASE_STATUS.md), [the architecture overview](docs/architecture/system-overview.md), and [the decision log](docs/DECISIONS.md).

## Requirements

- Python 3.11 or newer, below 3.15. Python 3.12 is the recommended local runtime for ML package compatibility.
- Git.
- PostgreSQL 16 is required to run the control-plane migrations. Docker is one local option; native PostgreSQL also works.

No global Python packages are required. All Python packages install inside a project virtual environment. The two Transformer model artifacts total about 955 MB and download once into the ignored `models/` directory. The spaCy English small NER package is about 13 MB and installs into `.venv`.

## Local setup

Run these commands from the repository root.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev,ml,pii]"
cp .env.example .env
python -m spacy download en_core_web_sm
python scripts/download_model.py
python scripts/download_prompt_injection_model.py
python -m guardrail_mini
```

On Windows PowerShell, activate the environment with `.venv\Scripts\Activate.ps1`. On Windows Command Prompt, use `.venv\Scripts\activate.bat`. If Python 3.12 is not available, install Python 3.12 or use another supported version with the matching `python` command.

The two download scripts verify their pinned Hugging Face revisions and Apache-2.0 metadata, then write SHA-256 checksums into each model directory. Presidio and spaCy provide the English PII recognizers; they run locally with email, phone, SSN, credit-card, IP, person, and location checks. The API loads only local model files, verifies every checksum, and performs warm-up inferences before reporting ready. It never downloads a model during a request.

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

The evaluate response includes a score in `[0, 1]` per policy, configured thresholds, a combined `ALLOW`, `REVIEW`, or `BLOCK` action, model revisions, a request ID, and latency. Each policy defaults to a block threshold of `0.80` and review threshold of `0.55`; policy-specific environment variables are in `.env.example`. Policies default to `toxicity`; select any subset with `"policies": ["toxicity", "pii", "prompt_injection"]`. The catalog is available at `/v1/policies`. The automatic tests run with:

```bash
pytest
```

## PostgreSQL control plane

Start a local PostgreSQL 16 container from the repository root:

```bash
docker run -d --name guardrail-postgres \
  -e POSTGRES_USER=guardrail \
  -e POSTGRES_PASSWORD=guardrail_dev_only \
  -e POSTGRES_DB=guardrail \
  -p 5432:5432 \
  -v guardrail-postgres-data:/var/lib/postgresql/data \
  --health-cmd='pg_isready -U guardrail -d guardrail' \
  --health-interval=5s --health-timeout=3s --health-retries=10 \
  postgres:16
```

Copy `.env.example` to `.env`, then set:

```dotenv
GUARDRAIL_DATABASE_URL=postgresql+psycopg://guardrail:guardrail_dev_only@localhost:5432/guardrail
```

Apply and inspect the schema:

```bash
alembic upgrade head
alembic current
docker exec -it guardrail-postgres psql -U guardrail -d guardrail -c '\\dt'
```

The migration creates tenant and project ownership, API-key hash/status fields, global policy metadata, per-project policy overrides, and versioned model metadata. The raw API key is not a database field. Detailed PostgreSQL setup, migration, inspection, and development reset steps are in [docs/DATABASE.md](docs/DATABASE.md).

## Project map

```text
src/guardrail_mini/     application, API, policy/model code, and SQLAlchemy schema
scripts/                model artifact setup scripts
tests/                  automated tests
docs/architecture/      architecture and request-flow notes
docs/DECISIONS.md       major implementation choices
migrations/             Alembic schema revisions
```

## Planned implementation

Later phases add API-key authentication, MinIO model artifact storage, observability, Docker Compose, load testing, CI, and a public deployment. This README will be updated as each phase is implemented and verified.
