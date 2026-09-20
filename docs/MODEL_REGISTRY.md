# MinIO Model Registry

Phase 6 stores versioned Transformer artifacts in MinIO through the standard S3 API. PostgreSQL stores each model's ID, version, framework, S3 URI, manifest checksum, and metrics metadata. The API resolves those rows once during startup, fetches any missing model files to a local cache, verifies the manifest and every file checksum, loads the classifiers, and warms them before `/ready` succeeds. Inference handlers never call MinIO or download model files.

With `GUARDRAIL_MODEL_RUNTIME=onnxruntime`, startup also creates or reuses a derived float32 ONNX graph under `GUARDRAIL_ONNX_CACHE_DIR` after validating the source artifact. The cache key includes the manifest digest and PyTorch, ONNX, ONNX Script, and ONNX Runtime versions. Generated graphs are not uploaded to MinIO and do not replace the verified source weights. First-time export happens before readiness; later startups use the cached graph. The two graph files add about 959 MiB. See [the Phase 10 profile](performance/phase10-profile.md) for measured latency and score comparisons.

## Current MinIO distribution note

As of September 2026, the upstream MinIO community server repository is archived and its README says future community builds are source-only; its Homebrew formula is deprecated. This project pins the last tagged community release for a local portfolio demo and keeps its application client on the S3 API. Do not use this pinned community server as a new public production dependency; use a maintained object store such as managed S3 for deployment. See the [upstream repository status](https://github.com/minio/minio) and [Homebrew formula](https://github.com/Homebrew/homebrew-core/blob/HEAD/Formula/m/minio.rb).

The precompiled Homebrew binary crashes during the Apple Silicon CPU probe in this environment. A CGO-disabled source build runs correctly. From the repository root on macOS or Linux:

```bash
brew install go
CGO_ENABLED=0 GOBIN="$(pwd)/.venv/bin" go install github.com/minio/minio@RELEASE.2025-10-15T17-29-55Z
```

This builds the exact upstream release tag with the Go toolchain. On Windows PowerShell, install Go 1.24 or later, then run:

```powershell
$env:CGO_ENABLED = "0"
$env:GOBIN = (Join-Path $PWD ".venv\Scripts")
go install github.com/minio/minio@RELEASE.2025-10-15T17-29-55Z
```

## Configure local credentials

Use a unique local development access key and secret. Put them in `.env`, which is ignored by Git:

```dotenv
GUARDRAIL_DATABASE_URL=postgresql+psycopg://guardrail_user:local_dev_only@localhost:5432/guardrail
GUARDRAIL_MINIO_ENDPOINT_URL=http://127.0.0.1:9000
GUARDRAIL_MINIO_ACCESS_KEY=replace_with_local_access_key
GUARDRAIL_MINIO_SECRET_KEY=replace_with_random_local_secret
GUARDRAIL_MINIO_BUCKET=guardrail-models
GUARDRAIL_ARTIFACT_CACHE_DIR=data/model-cache
```

Set the MinIO server's `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD` to the same access key and secret. The root credentials are for this single-user local demo. Production deployments should use scoped credentials or workload identity instead.

## Start, upload, and load artifacts

With PostgreSQL running and `alembic upgrade head` already applied, run in separate terminals from the repository root:

```bash
python scripts/run_minio_dev.py
```

MinIO serves the S3 API on `http://127.0.0.1:9000` and the console on `http://127.0.0.1:9001`. The server prints its API and console addresses. `Ctrl+C` stops the local process; files stay under ignored `data/minio-data/`.

Download the pinned model artifacts from Hugging Face once if needed, then upload and register them:

```bash
python scripts/download_model.py
python scripts/download_prompt_injection_model.py
python scripts/upload_models_to_minio.py
```

The upload command creates the bucket if missing, enables S3 bucket versioning, verifies the local source manifests, and writes objects beneath:

```text
guardrail-models/
  models/unitary/toxic-bert/v1/
  models/patronus-studio/wolf-defender-prompt-injection-small/v1/
```

The database row's `artifact_uri` points at that immutable model/version prefix. Re-running the upload is idempotent if bytes match; it refuses to replace an object or database version with different bytes. Each manifest digest is saved in PostgreSQL. On API startup the registry pulls only registered files into `data/model-cache/`; it validates the expected model ID, pinned upstream revision, database manifest digest, and each artifact's SHA-256 before model loading.

Start the API only after both model rows and objects exist:

```bash
python -m guardrail_mini
```

Readiness means the registry metadata was found, model files were verified and loaded, and warm-up completed. If MinIO or PostgreSQL is unreachable and the verified local cache is absent, startup fails and `/ready` remains unavailable. Once startup succeeds, stopping MinIO does not interrupt evaluation requests; model weights stay in process memory. A later restart can use a valid local cache, but still needs PostgreSQL to resolve the selected version.

## Inspect the registry

```bash
psql postgresql://guardrail_user:local_dev_only@localhost:5432/guardrail \
  -c 'SELECT model_id, version, framework, artifact_uri, checksum FROM model_versions ORDER BY model_id;'
```

The checksum covers the JSON manifest, whose own entries cover every tokenizer and weight file. S3 bucket versioning preserves previous object revisions at the storage layer; model IDs and `v1`, `v2`, and later paths preserve the application-visible release history.
