# Observability

Phase 8 adds request correlation, structured application logs, Prometheus metrics, and a provisioned Grafana overview dashboard.

## Request IDs and logs

Every HTTP response includes `X-Request-ID`. A valid client-provided ID containing 1–64 ASCII letters, digits, periods, underscores, or hyphens is retained. Missing or invalid IDs are replaced with a generated `req_` ID. Evaluation responses use the same ID in their JSON body.

Application request logs are JSON and include the request ID, tenant/project IDs when authenticated, method, route template, status, and elapsed milliseconds. The formatter allowlists fields. It does not record request bodies, query parameters, authorization headers, detected PII values, or model input text. Validation errors return a stable message and do not echo submitted values. Set `GUARDRAIL_LOG_LEVEL` to adjust application log verbosity.

## Metrics

`GET /metrics` exposes the Prometheus text format. It is a separate endpoint and does not evaluate input. Metrics use route templates and stable policy/error labels to keep cardinality bounded.

| Metric | Type | Labels / meaning |
| --- | --- | --- |
| `guardrail_requests_total` | Counter | HTTP method, route template, status code |
| `guardrail_request_duration_seconds` | Histogram | End-to-end HTTP latency by method and route |
| `guardrail_policy_evaluations_total` | Counter | Completed policy decisions by policy and action |
| `guardrail_policy_latency_seconds` | Histogram | Full policy implementation latency |
| `guardrail_model_inference_latency_seconds` | Histogram | Model inference or local PII/NLP analysis latency |
| `guardrail_errors_total` | Counter | Stable API error code |

The policy latency includes policy scoring and threshold decision work. The inference histogram measures the classifier or PII analyzer call. Startup warm-up is not included.

## Prometheus and Grafana

Provisioning files live under `monitoring/`. Prometheus scrapes `api:8000/metrics` on the Compose network. Grafana automatically provisions that Prometheus data source and the **Guardrail Mini Overview** dashboard with request rate, request p95, policy action volume, policy p95, inference p95, and API error rate panels.

Start the full stack with `docker compose up -d`. Open Prometheus at `http://127.0.0.1:9090` and Grafana at `http://127.0.0.1:3000`. The dashboard is provisioned from source and can be edited in Grafana; changes intended to persist should be copied back to `monitoring/grafana/dashboards/guardrail-overview.json`. See [DOCKER.md](DOCKER.md) for service startup and health checks.

Inspect metrics from a locally running API with `curl http://127.0.0.1:8000/metrics`. The Prometheus target configuration uses the Compose service name and is not a host-local scrape configuration.
