# Resume bullets

Choose the bullets that match the role and keep the benchmark caveat if quoting throughput.

- Built a Python/FastAPI guardrail service with project-scoped API keys and toxicity, PII, and prompt-injection policies, backed by PostgreSQL and checksum-verified model artifacts.
- Profiled CPU model inference and introduced cached float32 ONNX graphs; measured 6.1× lower toxicity p50 and 3.9× lower prompt-injection p50 than PyTorch on the recorded local workload.
- Benchmarked authenticated, three-policy API traffic with k6; sustained 50 requests/s for 30 seconds without HTTP errors or dropped iterations on an Apple M5 Pro Docker host.
- Reduced local 10-RPS p95 from 553 ms to 30 ms by limiting the ONNX thread pool from 15 to 2, while average API CPU fell from 14.15 to 0.82 cores.
- Added a Docker Compose development stack for the API, PostgreSQL, MinIO, Prometheus, and Grafana, plus GitHub Actions for model-backed tests, lint, formatting, and type checks.

The latency and throughput figures describe these specific local profiles. They are not production SLOs or public deployment results.
