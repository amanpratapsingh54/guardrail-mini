# Docker Compose

Phase 11 packages the API and starts its local control plane, model artifact store, and monitoring stack. Compose creates the database schema, downloads the pinned models into a named volume when needed, registers them in MinIO, and waits for the API readiness check before starting Prometheus.

## Requirements

- Docker Engine with the Docker Compose plugin (Compose v2.24 or newer).
- Enough free disk space for the Python/ML image, about 955 MB of source model files, about 959 MiB of derived ONNX graphs, and the PostgreSQL, MinIO, Prometheus, and Grafana volumes.
- Network access to Docker image registries, Go module sources, and Hugging Face on the first build and model download.

The checked-in `.env.example` values are local development credentials. Compose binds service ports to `127.0.0.1`. Change the credentials in `.env` before using the stack on a shared machine.

The MinIO image is built locally from the pinned upstream `RELEASE.2025-10-15T17-29-55Z` source tag because upstream no longer publishes that community container image. Compose publishes PostgreSQL on host port 5433 and MinIO on 9002/9003 by default to avoid common local PostgreSQL and MinIO ports; change `POSTGRES_HOST_PORT`, `MINIO_API_HOST_PORT`, or `MINIO_CONSOLE_HOST_PORT` in `.env` if needed.

## Build and start

Run from the repository root:

```bash
cp .env.example .env
docker compose build
docker compose up -d
docker compose ps
```

On the first start, `model-init` downloads the two pinned Hugging Face artifacts if the model volume is empty, verifies their manifests, and uploads/registers them in MinIO. The API then verifies those registered artifacts, exports or reuses the ONNX graphs, loads the PII recognizer, and warms the policies before `/ready` returns HTTP 200. This first start can take several minutes and uses roughly 2 GB for source and derived model files.

Follow startup logs:

```bash
docker compose logs -f model-init api
```

Inspect a service, all container states, or the API health check:

```bash
docker compose ps
docker compose logs --tail=100 postgres minio api prometheus grafana
docker inspect --format '{{json .State.Health}}' "$(docker compose ps -q api)"
curl http://127.0.0.1:8000/ready
curl http://127.0.0.1:9002/minio/health/ready
```

PostgreSQL uses `pg_isready`. The API health check calls `/ready`. The model setup process polls MinIO's readiness endpoint before upload because the MinIO image does not include a shell HTTP client for a container-local health check.

## Service URLs

| Service | URL | Purpose |
| --- | --- | --- |
| Guardrail API and Swagger | <http://127.0.0.1:8000/docs> | Inference API and health routes |
| PostgreSQL | `127.0.0.1:5433` | Control-plane database |
| MinIO S3 API | <http://127.0.0.1:9002> | Model artifact storage |
| MinIO console | <http://127.0.0.1:9003> | Local object-store administration |
| Prometheus | <http://127.0.0.1:9090> | Metrics and scrape status |
| Grafana | <http://127.0.0.1:3000> | Provisioned dashboard |

Grafana defaults are in `.env.example`; the dashboard is **Guardrail Mini Overview**. The API listens on `0.0.0.0` inside its container while the published host port is loopback-only.

## Create an API key and evaluate text

After `docker compose ps` reports the API healthy, create a local project and key:

```bash
docker compose run --rm api python scripts/bootstrap_dev_project.py
docker compose run --rm api python scripts/create_api_key.py \
  --project-id <PROJECT_ID_FROM_OUTPUT> \
  --name local-development
```

Save the one-time key printed by the second command, then call the API from the repository terminal:

```bash
export GUARDRAIL_API_KEY='gr_live_replace_with_the_printed_key'
curl -X POST http://127.0.0.1:8000/v1/guardrails/evaluate \
  -H "Authorization: Bearer $GUARDRAIL_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"input":"Please summarize the public report.","policies":["toxicity","pii","prompt_injection"]}'
```

The expected response is HTTP 200 with an aggregate action and one result for each requested policy. A safe example should return `ALLOW`.

## Stop and reset

Stop the stack and retain its data:

```bash
docker compose down
```

To remove the PostgreSQL database, MinIO objects, downloaded model artifacts, ONNX cache, and monitoring data as well:

```bash
docker compose down --volumes
```

The second command permanently deletes the named local volumes. The services use development credentials and this Compose stack is intended for local evaluation; public deployment requires managed credentials, TLS, durable backups, and reviewed network exposure.
