# Guardrail Mini

A portfolio project for a small, production-minded guardrail API. It evaluates text with specialized policy implementations and returns `ALLOW`, `BLOCK`, or `REVIEW` decisions.

The first ten phases are complete: three real guardrail policies, PostgreSQL control-plane metadata, S3-compatible model artifacts, bearer API-key authentication, privacy-safe observability, bounded request bodies, per-project rate limits, failure-path tests, and a profiled ONNX Runtime backend. See the [Phase 10 profile](docs/performance/phase10-profile.md) for measured single-call latency, score parity, and the runtime trade-offs.

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
python -m pip install -e ".[dev,ml,pii,onnx]"
cp .env.example .env
python -m spacy download en_core_web_sm
python scripts/download_model.py
python scripts/download_prompt_injection_model.py
```

On Windows PowerShell, activate the environment with `.venv\Scripts\Activate.ps1`. On Windows Command Prompt, use `.venv\Scripts\activate.bat`. If Python 3.12 is not available, install Python 3.12 or use another supported version with the matching `python` command.

The two download scripts verify their pinned Hugging Face revisions and Apache-2.0 metadata, then write SHA-256 checksums into each model directory. Presidio and spaCy provide the English PII recognizers; they run locally with email, phone, SSN, credit-card, IP, person, and location checks. The API loads only local model files, verifies every checksum, and performs warm-up inferences before reporting ready. It never downloads a model during a request.

With the PyTorch backend, `GUARDRAIL_MODEL_DEVICE=auto` uses Metal (MPS) when available; otherwise it uses CPU. Set `GUARDRAIL_MODEL_DEVICE=cpu` in `.env` to force CPU inference. ONNX Runtime currently supports CPU only.

The example `.env` selects `GUARDRAIL_MODEL_RUNTIME=onnxruntime`, which runs the two Transformer classifiers through ONNX Runtime's CPU provider. At first startup, the service exports float32 ONNX graphs from the already verified local model artifacts and caches them under `data/onnx-cache/`; subsequent startups reuse the cache. This adds about 955 MB of local graph storage and export time before readiness. Set `GUARDRAIL_MODEL_RUNTIME=pytorch` to use the original PyTorch backend. See the profile for the measured latency and score comparison.

## Check the API

With the server running, open <http://127.0.0.1:8000/docs> for Swagger UI or run:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/live
curl http://127.0.0.1:8000/ready
curl -X POST http://127.0.0.1:8000/v1/guardrails/evaluate \
  -H "Authorization: Bearer $GUARDRAIL_API_KEY" \
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

## API-key authentication

The evaluate and API-key management routes require `Authorization: Bearer <key>`. After PostgreSQL migrations, create a development tenant/project and the first credential from a trusted local shell:

```bash
python scripts/bootstrap_dev_project.py
python scripts/create_api_key.py --project-id <PROJECT_ID_FROM_OUTPUT> --name local-development
```

The key creation command prints the raw token once. Save it in your local environment as `GUARDRAIL_API_KEY`, then start the server:

```bash
python -m guardrail_mini
```

Subsequent project keys can be created with `POST /v1/api-keys` and revoked with `DELETE /v1/api-keys/{id}`. Each is scoped to the authenticated project's ID. PostgreSQL stores only SHA-256 hashes, key prefixes, active state, expiry, and last-use time. A 30-second in-process cache limits normal validation traffic to occasional database lookups; revocation in another worker can take up to that TTL to take effect. See [docs/AUTHENTICATION.md](docs/AUTHENTICATION.md) for request and response examples.

## Observability

Responses include `X-Request-ID`; evaluation JSON carries the same ID. Application logs are JSON and omit request text, query parameters, and credentials. Prometheus metrics are available at `/metrics`. Prometheus and Grafana provisioning, dashboard panels, metric definitions, and Compose connection details are in [docs/OBSERVABILITY.md](docs/OBSERVABILITY.md).

The API caps request bodies and applies a per-project evaluation rate limit. CORS is disabled until a trusted browser origin is explicitly configured at an HTTPS gateway. See [docs/SECURITY.md](docs/SECURITY.md) for limits and deployment security requirements.

Run the dependency advisory check after installing development extras:

```bash
pip-audit
```

## MinIO model artifacts

MinIO is used as a local S3-compatible artifact store. The current community server repository is archived; this project uses a pinned local build for evaluation and the generic S3 API, with managed S3 intended for public deployment. The source build, local credentials, bucket layout, upload command, startup loading, checksum validation, and cache behavior are documented in [docs/MODEL_REGISTRY.md](docs/MODEL_REGISTRY.md).

After configuring PostgreSQL and the MinIO variables in `.env`, start MinIO in one terminal:

```bash
python scripts/run_minio_dev.py
```

From a second repository-root terminal, upload and register the already downloaded artifacts:

```bash
python scripts/upload_models_to_minio.py
```

Then start the API with `python -m guardrail_mini`. On startup it resolves the two model versions from PostgreSQL, downloads them from MinIO only if the verified local cache is missing, validates checksums, and warms the models before readiness. Evaluation requests use in-memory models and do not access MinIO.

## Project map

```text
src/guardrail_mini/     application, API, policy/model code, and SQLAlchemy schema
scripts/                model artifact setup and inference profiling scripts
tests/                  automated tests
docs/architecture/      architecture and request-flow notes
docs/MODEL_REGISTRY.md  MinIO setup and model artifact lifecycle
docs/DATABASE.md        PostgreSQL setup and migration instructions
docs/AUTHENTICATION.md  API-key lifecycle and tenant/project scope
docs/OBSERVABILITY.md  request IDs, structured logs, metrics, and dashboards
docs/SECURITY.md       request limits, API keys, CORS, and deployment security
docs/performance/      measured inference runtime comparison
monitoring/             Prometheus and Grafana provisioning and dashboard
docs/DECISIONS.md       major implementation choices
migrations/             Alembic schema revisions
```

## Planned implementation

Later phases add Docker Compose, load testing, CI, and a public deployment. This README will be updated as each phase is implemented and verified.
