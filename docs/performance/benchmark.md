# Phase 12 — API Load Benchmark

## Result

The Compose API sustained **50 requests per second** for 30 seconds with all three policies selected. It completed 1,501 requests at 49.97 requests/s with no HTTP failures or dropped iterations. End-to-end latency was 34.44 ms p50, 59.24 ms p95, and 105.47 ms p99.

The 75 requests/s stage saturated: actual throughput fell to 66.17 requests/s, k6 dropped 113 scheduled iterations, and end-to-end p95 reached 3.67 seconds. At 100 requests/s the API completed 1,736 requests at 59.37 requests/s, dropped 810 iterations, and reached 6.61 seconds p95. Both overload stages returned HTTP 200 for completed requests and left the API healthy; the offered arrival rate exceeded service capacity.

| Target RPS | Actual RPS | HTTP errors | Dropped iterations | p50 | p95 | p99 | API CPU avg. |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 10.00 | 0% | 0 | 28.42 ms | 30.47 ms | 34.08 ms | 0.82 cores |
| 20 | 20.01 | 0% | 0 | 28.50 ms | 31.49 ms | 47.46 ms | 1.62 cores |
| 50 | 49.97 | 0% | 0 | 34.44 ms | 59.24 ms | 105.47 ms | 3.80 cores |
| 75 | 66.17 | 0% | 113 | 2.73 s | 3.67 s | 3.96 s | 7.26 cores |
| 100 | 59.37 | 0% | 810 | 5.76 s | 6.61 s | 6.95 s | 7.44 cores |

The CPU column is the average API container CPU time from cgroup `usage_usec` deltas over each 30-second stage (the 100 RPS run was stopped at 29.3 seconds). The API container's cgroup memory high-water mark over startup and these stages was 2.10 GiB; after the 75 RPS stage it used 1.80 GiB. Docker Engine reported 15 CPUs and 7.75 GiB of memory.

## Workload and environment

- Host: Apple M5 Pro, arm64 macOS; k6 and Docker Desktop ran on the same machine.
- Docker Engine: 15 CPUs and 7.75 GiB memory available to containers.
- API: Python 3.12, CPU-only ONNX Runtime, one Uvicorn process, and `OMP_NUM_THREADS=2`.
- Models: `unitary/toxic-bert@4d6c22e74ba2fdd26bc4f7238f50766b045a0d94`, `patronus-studio/wolf-defender-prompt-injection-small@cdcdf7d0231d68f39cc3bb1b70f6a2bdfca8ad55`, and Presidio 2.2.364 with `en_core_web_sm` 3.8.0.
- Each request used a local bearer key and evaluated `toxicity`, `pii`, and `prompt_injection` against the fixed benign text `Please summarize the public report.`
- Each stage used k6's `constant-arrival-rate` executor for 30 seconds, with p50, p95, and p99 collected. The test checked for HTTP 200 and all requested policy results. It thresholds HTTP errors below 1% and requires zero dropped iterations.
- k6 version: 2.2.0 on macOS arm64. Install it from [Grafana's k6 instructions](https://grafana.com/docs/k6/latest/set-up/install-k6/). The [k6 options reference](https://grafana.com/docs/k6/latest/using-k6/k6-options/reference/) documents summary percentile configuration.

## Thread-pool comparison

Before tuning, PyTorch reported 15 threads in the API container, and each ONNX Runtime session used that value for its intra-op pool. At 10 RPS, the measured HTTP p50/p95/p99 were 321/553/678 ms; the API used an average 14.15 CPU cores. Setting `OMP_NUM_THREADS=2` reduced them to 28/30/34 ms and average API CPU to 0.82 cores, with no failed requests or dropped iterations. Compose now defaults this variable to 2; change it in `.env` only when measuring a different thread setting.

The response's `latency_ms` starts timing inside the synchronous evaluation handler, after request parsing and authentication. The k6 script also records end-to-end request duration and estimates the time outside that handler by subtracting `latency_ms`. At 10–50 RPS this estimate stayed below 5 ms p95. In the 75 and 100 RPS overload runs it rose to about 3.03 and 5.88 seconds p95, while the API-reported policy path was about 1.04 and 1.08 seconds p95. This points to request queueing and framework scheduling during overload.

Prometheus' per-policy inference histogram over the five-minute window containing the saturation runs showed:

| Policy | Mean inference latency | p95 inference latency |
| --- | ---: | ---: |
| Toxicity | 48 ms | 88 ms |
| PII / Presidio | 476 ms | 987 ms |
| Prompt injection | 25 ms | 52 ms |

The PII detector was the largest policy-side contributor in that high-load window. The metrics include each policy's local inference call, including tokenization or NLP analysis. PostgreSQL and MinIO are not accessed in the evaluation request path. The remaining request-path queue and the PII detector are the next optimization targets; the shared load generator may also compete for CPU with the API.

## Reproduce

Start the local stack as described in [the Docker guide](../DOCKER.md), create a project key, then temporarily raise the Compose API rate limit above the default 600 requests/minute. This benchmark used 12,000 requests/minute so the limiter would not constrain the 100 RPS stage.

```bash
GUARDRAIL_RATE_LIMIT_REQUESTS_PER_MINUTE=12000 docker compose --env-file .env.example up -d --no-deps --force-recreate api
export API_KEY='paste-the-one-time-local-key-here'

BASE_URL=http://127.0.0.1:8000 RATE=10 DURATION=30s \
  k6 run --summary-export=/tmp/guardrail-10rps.json scripts/loadtest.js
BASE_URL=http://127.0.0.1:8000 RATE=20 DURATION=30s \
  k6 run --summary-export=/tmp/guardrail-20rps.json scripts/loadtest.js
BASE_URL=http://127.0.0.1:8000 RATE=50 DURATION=30s \
  k6 run --summary-export=/tmp/guardrail-50rps.json scripts/loadtest.js
BASE_URL=http://127.0.0.1:8000 RATE=75 DURATION=30s \
  k6 run --summary-export=/tmp/guardrail-75rps.json scripts/loadtest.js
BASE_URL=http://127.0.0.1:8000 RATE=100 DURATION=30s \
  k6 run --summary-export=/tmp/guardrail-100rps.json scripts/loadtest.js

unset API_KEY GUARDRAIL_RATE_LIMIT_REQUESTS_PER_MINUTE
docker compose --env-file .env.example up -d --no-deps --force-recreate api
```

Run `docker stats` in a second terminal during a stage to observe container memory and CPU. The benchmark's CPU values above came from API cgroup CPU counters, which avoid interpreting instantaneous Docker CPU percentages. The Compose API returns to its default 600 requests/minute limit after the final command.

## Limits and bottleneck analysis

The 50 RPS result is the highest tested rate with no dropped iterations. The service's saturation knee is between 50 and 75 RPS for this combined-policy workload on this host. The single-machine k6 generator shares CPU with Docker Desktop, so the overload results are conservative and need confirmation with a separate load generator. These short runs are capacity probes, not production SLOs or capacity claims.

The initial 15-thread ONNX setting oversubscribed the container during concurrent inference. The two-thread setting addressed that CPU contention. Under heavier offered load, the API path then queued before the handler and PII analysis grew sharply. Follow-up work should measure longer steady-state runs from a remote generator, isolate per-policy loads, and compare bounded thread-pool and process-worker settings while accounting for each process's roughly 2 GiB model footprint. No result here supports a 100 RPS production claim.
