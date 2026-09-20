# Phase 10: Inference Profile and ONNX Runtime

## Result

On this machine, ONNX Runtime's CPU provider reduced warmed, serial score latency for both Transformer policies while preserving decisions on the tested examples. The example `.env` selects ONNX Runtime. PyTorch remains available with `GUARDRAIL_MODEL_RUNTIME=pytorch`.

| Policy | Backend | Mean | p50 | p95 | p99 | Serial scores/s |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Toxicity | PyTorch CPU | 36.848 ms | 36.952 ms | 38.950 ms | 39.116 ms | 27.139 |
| Toxicity | ONNX Runtime CPU, float32 | 6.077 ms | 6.050 ms | 6.508 ms | 6.556 ms | 164.552 |
| Prompt injection | PyTorch CPU | 30.555 ms | 30.366 ms | 34.113 ms | 35.071 ms | 32.728 |
| Prompt injection | ONNX Runtime CPU, float32 | 8.116 ms | 7.795 ms | 11.474 ms | 12.305 ms | 123.210 |

These are score-call measurements, not end-to-end API or concurrent throughput results. The toxicity p50 improved by about 6.1x and prompt injection by about 3.9x in this paired run. A separate baseline profile measured the PII policy at 6.727 ms p50 and 7.053 ms p95; PII uses Presidio and spaCy and does not use ONNX.

## Method and environment

- Hardware: Apple M5 Pro, macOS 26.6.2, arm64. PyTorch reported MPS unavailable, so both model backends used CPU.
- Runtime: Python 3.12.10, PyTorch 2.14.0, ONNX 1.23.0, ONNX Runtime 1.30.0, five PyTorch threads.
- Models: `unitary/toxic-bert` revision `4d6c22e74ba2fdd26bc4f7238f50766b045a0d94`; `patronus-studio/wolf-defender-prompt-injection-small` revision `cdcdf7d0231d68f39cc3bb1b70f6a2bdfca8ad55`.
- Each backend used five warm-up calls followed by 30 serial calls. Timing includes tokenization and one model score per call. The paired benchmark scores five short fixed examples and one 9,998-character input; tokenization truncates that long input at each model's configured maximum. Timings use the five short examples.
- Commands from the repository root:

  ```bash
  .venv/bin/python scripts/profile_inference.py --warmup 5 --iterations 30
  .venv/bin/python scripts/benchmark_onnx.py toxicity --warmup 5 --iterations 30
  .venv/bin/python scripts/benchmark_onnx.py prompt_injection --warmup 5 --iterations 30
  ```

  `profile_inference.py` measures the original PyTorch policies, including PII. `benchmark_onnx.py` performs the paired PyTorch/ONNX comparison and emits the runtime versions, latencies, artifact sizes, and score comparison as JSON.

## Score and decision checks

The Dynamo-exported float32 graph's maximum absolute score delta, rounded to six decimal places, was `0.000001` for both models across the six fixed examples. At the 9,998-character input, toxicity scored `0.202750` in PyTorch and `0.202749` in ONNX; prompt injection scored `0.963622` in both. The benchmark's `ALLOW`/`REVIEW`/`BLOCK` actions matched on every example. The authenticated API test also evaluated all three policies through the ONNX configuration, checked a prompt-injection block, and exercised input that tokenizes beyond the models' maximum lengths and is truncated.

Dynamic INT8 was not selected. ONNX Runtime's dynamic quantizer currently fails shape inference on the Dynamo-exported graphs. A separate earlier INT8 probe on legacy-exported graphs completed, but prompt-injection scores shifted by as much as 0.107091 on the same example set, so its scores were not safe to substitute. Keep the float32 graphs until a quantization path passes score and decision checks.

## Startup, storage, and request path

The measured float32 graph files were 419.44 MiB for toxicity and 539.54 MiB for prompt injection, about 959 MiB total. Export took 4.357 seconds and 11.757 seconds respectively in the benchmark process. First-time export happens after source artifact checksum validation and before `/ready` succeeds. It adds startup delay and derived disk usage; later starts reuse the cache. Model export and downloads never happen on an evaluation request.

The runtime uses PyTorch's `dynamo=True` exporter with opset 18 and a single-file graph. This follows the [PyTorch ONNX export tutorial](https://docs.pytorch.org/tutorials/beginner/onnx/export_simple_model_to_onnx_tutorial.html), which presents the newer `torch.export`-based exporter. The graph runs through ONNX Runtime's [CPU execution provider](https://onnxruntime.ai/docs/api/python/api_summary.html).

The cache identity includes the source manifest digest and PyTorch, ONNX, and ONNX Runtime versions. Cache files live under the ignored `data/onnx-cache/` directory and do not replace or modify the verified source artifacts. ONNX Runtime currently uses the CPU provider only; the PyTorch backend remains available where MPS or another device is needed.

## Limits of this result

The run used 30 serial observations per backend on one machine. It does not measure HTTP routing, authentication, PostgreSQL, MinIO, concurrency, memory under multiple workers, or tail behavior under load. Serial scores per second is the reciprocal of the measured mean latency; it is not a service capacity claim. Phase 12 must measure request throughput, errors, resource use, and end-to-end latency under reproducible load before making capacity statements.
