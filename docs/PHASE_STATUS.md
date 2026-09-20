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

## Phase 5 — Persistence

**Status: complete.** Added SQLAlchemy 2 models and an Alembic migration for tenants, projects, hashed API-key records, global policy metadata, project policy overrides, and model versions/checksums/metrics. Alembic requires an explicit `GUARDRAIL_DATABASE_URL` from the environment or `.env`; PostgreSQL uses the Psycopg 3 driver.

The policy registry remains cached in process. Model version rows are read during startup in Phase 6; Phase 7 uses PostgreSQL for key validation on cache misses and project-scoped key management. See [DATABASE.md](DATABASE.md) for setup and operations.

Verification on Python 3.12.10:

- `pytest`: 16 passed; the migration test creates every expected table, writes tenant/project/policy/API-key/model records, and downgrades to base using temporary SQLite.
- PostgreSQL 16.15 on macOS: Alembic upgrade/current/check/downgrade/re-upgrade passed; `alembic check` detected no schema drift.
- PostgreSQL ORM transaction: tenant/project, hashed key metadata, policy override, and JSON model metrics inserted and queried successfully, then rolled back.

## Phase 6 — Model registry

**Status: complete.** Added an S3-compatible storage client, idempotent model upload and PostgreSQL registration, bucket versioning, local MinIO launcher, and startup retrieval into an ignored cache. The API requires an exact database registry row for each pinned model when MinIO mode is enabled. It checks the database's manifest digest and every manifest file checksum before loading models and warming inference. The existing local Hugging Face path remains available when MinIO settings are absent.

MinIO community server is used for local evaluation only. Its upstream repository was archived in April 2026, so the project uses a pinned source build and standard S3 API; managed S3 is preferred for deployment. See [MODEL_REGISTRY.md](MODEL_REGISTRY.md) and the [decision log](DECISIONS.md).

Verification on Python 3.12.10 and macOS arm64:

- `pytest`: 27 passed, including MinIO configuration validation, S3 URI scoping, and manifest path safety.
- `ruff check .`, `ruff format --check .`, and `mypy src tests scripts migrations`: passed.
- MinIO `RELEASE.2025-10-15T17-29-55Z` source build with `CGO_ENABLED=0`: started locally after the Homebrew binary's CPU probe crashed.
- Uploaded both pinned models to the versioned bucket and registered both PostgreSQL rows. Re-upload is checksum-idempotent.
- API lifespan fetched artifacts from MinIO, validated checksums, loaded and warmed the real classifiers; a three-policy benign sample returned `ALLOW`, and a prompt-injection sample returned `BLOCK`.
- PostgreSQL registry migrations and ORM persistence were verified in Phase 5.

## Phase 7 — Authentication and project scope

**Status: complete.** Evaluations and API-key management require bearer API keys. Keys use 256-bit random material; PostgreSQL stores only SHA-256 hashes and non-secret prefixes. Keys can be created for the authenticated project, optionally expire, and can be revoked only within that same project. A trusted local CLI bootstraps the first tenant/project and key. Successful evaluation responses include tenant and project IDs.

Authentication uses a bounded in-process cache with a 30-second positive TTL and up to 5-second negative TTL. Revocation clears the current process cache immediately; other workers can continue honoring an already cached key until its TTL ends. PostgreSQL is not queried on every evaluation. No Redis service was added.

Verification:

- `pytest`: 28 passed, including valid, missing, invalid, expired, revoked, and cross-project key requests; key creation confirms the raw token is not persisted.
- The real-model end-to-end test now exercises bearer authentication, policy inference, aggregation, tenant/project context, and structured unknown-policy errors.
- PostgreSQL 16.15 manual end-to-end check passed for auth, model inference, key creation/revocation, and rejected use after revoke; the temporary tenant, project, and keys were removed afterward.
- `ruff check .`, `ruff format --check .`, and `mypy src tests scripts migrations`: passed.

See [AUTHENTICATION.md](AUTHENTICATION.md) for first-key setup, endpoint examples, expiration, and cache behavior.

## Phase 8 — Observability

**Status: complete.** Added response/request correlation IDs, JSON request and error logs with an explicit field allowlist, request/policy/model latency histograms, decision/error counters, `/metrics`, and provisioned Prometheus/Grafana configurations with an overview dashboard. Request bodies, query strings, credentials, and detected PII values are not logged. Metrics use route templates and stable IDs/codes rather than input-derived labels.

The Prometheus target and Grafana datasource/dashboard provisioning are ready for the Docker Compose services in Phase 11. Until then, `/metrics` can be inspected directly from a locally running API.

Verification:

- `pytest`: 32 passed. Tests cover accepted/generated request IDs, matching IDs in evaluation responses, invalid-body privacy, safe unexpected-error responses, the JSON log allowlist, metric exposition, and real-model policy/inference observations.
- `ruff check .`, `ruff format --check .`, and `mypy src tests scripts migrations`: passed.
- Prometheus and Grafana YAML provisioning files parse, and the Grafana dashboard JSON validates.

## Phase 9 — Testing and hardening

**Status: complete.** Added a 64 KiB default HTTP body cap (configurable from 1 KiB to 1 MiB), a bounded fixed-window per-project evaluation rate limit (600/minute by default), `Retry-After` responses, and stable `INFERENCE_TIMEOUT` mapping for model backends that raise `TimeoutError`. CORS stays disabled by default. Added failure tests for oversized bodies, rate limiting, timeouts, and missing database schema; documented API-key, body-size, rate-limit, CORS, TLS, and metrics endpoint security.

`pip-audit` is part of the development extras. On 2026-09-20 it reported no known vulnerabilities in the installed, PyPI-indexed environment after updating pip and pytest. The audit service cannot assess the locally installed spaCy model package (`en-core-web-sm`) or this unpublished project package because they are not present in its PyPI index.

Verification:

- `pytest`: 39 passed, including real model/API, policy, authentication, request-size, rate-limit, timeout, and startup failure coverage.
- `ruff check .`, `ruff format --check .`, and `mypy src tests scripts migrations`: passed.
- `pip-audit --cache-dir /private/tmp/guardrail-pip-audit`: no known vulnerabilities in indexed packages.
- The scan identified vulnerable `pip 25.0.1` and `pytest 8.4.2`; the environment now uses `pip 26.2.1` and `pytest 9.1.1`, and the declared pytest range requires `>=9.0.3`.

## Phase 10 — ONNX and performance optimization

**Status: complete.** Profiled the serial, warmed CPU inference path before evaluating ONNX Runtime. The paired ONNX float32 backend materially reduced per-call model score latency on both Transformer policies, with matching policy decisions across the fixed short and maximum-length examples. Dynamic INT8 quantization was rejected because it changed prompt-injection scores too much. ONNX export is performed from verified local artifacts at startup and stored in a versioned ignored cache; the request path does not export or download models. ONNX Runtime currently supports CPU only. See [the Phase 10 performance profile](performance/phase10-profile.md) for hardware, method, measured results, output parity, artifact size, and trade-offs.

The production cache uses PyTorch's `dynamo=True` ONNX exporter with opset 18 and dynamic batch/sequence dimensions. The resulting float32 graph is stored as one file; export completes before readiness.

Verification:

- `pytest`: 41 passed, including authenticated API inference through the ONNX backend for all three policies, model-maximum token lengths, and cache reuse without re-export.
- `ruff check .`, `ruff format --check .`, and `mypy src tests scripts migrations`: passed.
- `pip-audit` could not reach `pypi.org` because network name resolution is unavailable in this environment. A source advisory review found an ONNX converter vulnerability fixed in 1.22, so the optional dependency now requires `onnx>=1.22`; the installed version is 1.23.0. The full dependency audit still needs to run from a network-enabled environment. See the [ONNX advisory](https://github.com/onnx/onnx/security/advisories/GHSA-hwpq-hmq9-wj77).

## Next

## Phase 11 — Docker

**Status: complete.** Added a Python 3.12 API image, `.dockerignore`, and a Compose stack for the API, PostgreSQL, MinIO, Prometheus, and Grafana. Compose applies Alembic migrations, waits for MinIO, downloads and registers missing model artifacts, and waits for API readiness before starting Prometheus. Model, ONNX cache, database, object store, and monitoring data use named volumes. The MinIO container builds from the pinned upstream source tag because upstream no longer publishes the community image. Setup commands and service inspection steps are in [DOCKER.md](DOCKER.md).

Verification on Apple Silicon ARM64:

- `docker compose config --quiet`: passed; Compose lists all seven services.
- Built the CPU-only API image and the pinned MinIO source image.
- Started the stack from fresh named volumes. PostgreSQL became healthy, migrations and model preparation exited successfully, and both pinned model artifacts were downloaded, checksum-verified, and registered in MinIO.
- The API exported and cached its ONNX graphs, warmed all policies, and reported healthy; `GET /ready` returned HTTP 200.
- Prometheus reported the `guardrail-api` scrape target healthy. Grafana returned healthy and its provisioned **Guardrail Mini Overview** dashboard appeared in the dashboard API.
- A local bearer-key request through the Compose API evaluated toxicity, PII, and prompt injection; all returned `ALLOW` for the benign sample.
- Compose host ports for PostgreSQL and MinIO use 5433, 9002, and 9003 by default to avoid the local native services already occupying 5432, 9000, and 9001. The ports are configurable in `.env`.
- `pytest`: 43 passed; `ruff check .`, `ruff format --check .`, and `mypy src tests scripts migrations`: passed.

## Phase 12 — Load testing

**Status: complete.** Added a reproducible k6 constant-arrival-rate script for authenticated all-policy API requests and a measured benchmark report. The profile exposed ONNX intra-op thread oversubscription: limiting the Compose API to two threads reduced 10 RPS p95 from 553 ms to 30 ms and average API CPU from 14.15 to 0.82 cores. With that setting, 50 RPS remained stable; 75 and 100 RPS saturated the API and dropped scheduled iterations. Prometheus per-policy inference histograms identified PII analysis as the largest policy-side contributor during the saturation window. The benchmark records hardware, models, configuration, commands, results, resource method, and limitations in [performance/benchmark.md](performance/benchmark.md).

Verification:

- k6 v2.2.0 ran authenticated 30-second stages at 10, 20, 50, 75, and 100 RPS targets.
- At 10, 20, and 50 RPS, all policy checks passed with no HTTP failures or dropped iterations; throughput matched each target.
- At 75 and 100 RPS, completed requests remained HTTP 200, but k6 dropped 113 and 810 scheduled iterations respectively; the service returned to healthy status afterward.
- Container CPU was measured from cgroup CPU usage counter deltas; API memory high-water was 2.10 GiB.
- The Compose API rate limit was restored to its documented default of 600 requests/minute after testing.

## Next

Phase 13 adds GitHub Actions checks for the repository.
