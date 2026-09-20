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

## Next

Phase 8 adds structured logs, request IDs, Prometheus metrics, and a Grafana dashboard.
