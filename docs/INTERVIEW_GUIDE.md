# Interview guide

## 60-second overview

Guardrail Mini is a small, production-minded API for checking text against three separate policies: toxicity, personally identifiable information, and prompt injection. FastAPI authenticates a project-scoped bearer key, evaluates local classifiers, and combines the results into `ALLOW`, `REVIEW`, or `BLOCK`. PostgreSQL stores tenants, projects, key hashes, and model metadata. The local stack adds MinIO, Prometheus, and Grafana. I profiled both model runtimes, selected float32 ONNX for CPU inference, and measured the full API under authenticated load.

## Walk through the request

1. A client sends text and an optional policy list to `POST /v1/guardrails/evaluate` with a bearer key.
2. Middleware applies the request-body cap, assigns a request ID, and records safe operational fields.
3. Authentication validates the key hash, resolves its project, and caches the result briefly.
4. The policy engine evaluates the selected classifiers and aggregates the per-policy outcomes.
5. The response returns the action, per-policy score and categories, model revisions, request ID, and latency. PII values are never returned or logged.

At startup, the API validates its PostgreSQL schema, verifies model manifests and checksums, initializes the local PII recognizers, loads or exports the Transformer runtime, and warms each policy before `/ready` succeeds.

## Design decisions to explain

- **Separate policy implementations:** toxicity, PII, and prompt injection have different models, score meanings, and category outputs, so the service keeps them behind one registry interface instead of treating one classifier as a universal safety model.
- **`ANY_BLOCK` aggregation:** one high-confidence block signal is enough to block the request. Review thresholds keep uncertain results visible without silently allowing them.
- **High-entropy bearer keys:** the raw 256-bit key is shown once. PostgreSQL stores the SHA-256 hash and a non-secret prefix; project ownership scopes management and evaluation.
- **Short authentication cache:** ordinary evaluations avoid a database read each time. Revocation on a different process can take up to the 30-second cache TTL to take effect.
- **Immutable artifacts:** the model registry records exact revisions and manifest digests. Startup verifies all files before the model is available.
- **Float32 ONNX:** the local paired profile preserved scores and decisions on the fixed sample set. INT8 quantization was rejected after observed prompt-injection score drift.
- **Bounded local stack:** Docker Compose provides a reproducible API, database, artifact store, and monitoring environment without adding a distributed cache, Kubernetes, or training platform.

## Performance evidence

The Phase 10 serial profile measured toxicity p50 at 36.95 ms in PyTorch and 6.05 ms in ONNX; prompt-injection p50 was 30.37 ms and 7.80 ms respectively. These are warmed score-call measurements, not API capacity claims.

The Phase 12 combined-policy API load test sustained 50 requests/s for 30 seconds with no errors or dropped iterations. At the 75 requests/s target, throughput fell to 66.17 requests/s and k6 dropped 113 iterations. At 100 requests/s, the test completed 59.37 requests/s and dropped 810 iterations. The tests ran on the same Apple M5 Pro that hosted Docker, so they are a local baseline rather than a production SLO.

The initial ONNX sessions used 15 intra-op threads inside the container. At 10 requests/s that setting reached 553 ms p95 and averaged 14.15 CPU cores. Capping the pool at two threads reduced the same stage to 30 ms p95 and 0.82 average CPU cores. Under overload, Presidio/spaCy became the largest measured policy-side contributor. See the [benchmark report](performance/benchmark.md) for methods, full results, and limitations.

## Current limitations

- The per-project limiter is process-local. Replicas do not share an aggregate quota.
- Revocation cache invalidation is immediate only in the process that handled the revoke.
- Model scores are classifiers, not a complete security boundary; they can have false positives and false negatives.
- PII recognition is English-focused and some recognizers are US-specific.
- The API uses synchronous CPU inference. Capacity is bounded by model CPU, request queueing, and the host.
- The Cloud Run deployment guide and build are prepared, but public deployment requires a configured cloud account and database.
- The benchmark uses brief stages on a shared host and must not be represented as a production SLO.

## Likely follow-up questions

### Why not run the model directly in the request handler from a model hub?

The service pins revisions, verifies downloaded files before use, and never downloads on an evaluation request. Inference uses the already warmed in-process model, keeping network access and model initialization out of the request path.

### How would you improve performance next?

First, repeat the benchmark from a separate load generator and record longer steady-state intervals. Then isolate each policy, inspect PII recognizer costs, and compare bounded thread pools with process workers. Any extra worker must account for the roughly 2 GiB model-serving memory footprint. Recheck quality and tail latency before changing the runtime.

### What must change before a larger deployment?

Move rate limiting to a shared gateway or datastore, tune the database pool and model worker count, add a remote load test and explicit service-level objectives, confirm model quality on representative data, and exercise database restore and key rotation. Only then should replicas, autoscaling, GPU serving, or multi-region architecture be considered.

## References

- [System overview](architecture/system-overview.md)
- [Security notes](SECURITY.md)
- [Phase 10 model profile](performance/phase10-profile.md)
- [Phase 12 API benchmark](performance/benchmark.md)
- [Cloud deployment guide](DEPLOYMENT.md)
