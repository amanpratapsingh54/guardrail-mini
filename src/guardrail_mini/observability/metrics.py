"""Low-cardinality Prometheus metrics for requests, policies, and models."""

from prometheus_client import Counter, Histogram

REQUESTS_TOTAL = Counter(
    "guardrail_requests_total",
    "HTTP requests served by the guardrail API.",
    ["method", "route", "status_code"],
)
REQUEST_DURATION_SECONDS = Histogram(
    "guardrail_request_duration_seconds",
    "End-to-end HTTP request duration in seconds.",
    ["method", "route"],
)
POLICY_EVALUATIONS_TOTAL = Counter(
    "guardrail_policy_evaluations_total",
    "Completed policy evaluations by decision.",
    ["policy_id", "action"],
)
POLICY_LATENCY_SECONDS = Histogram(
    "guardrail_policy_latency_seconds",
    "Policy implementation latency in seconds.",
    ["policy_id"],
)
MODEL_INFERENCE_LATENCY_SECONDS = Histogram(
    "guardrail_model_inference_latency_seconds",
    "Policy model or local NLP inference latency, including tokenization where applicable.",
    ["policy_id"],
)
ERRORS_TOTAL = Counter(
    "guardrail_errors_total",
    "API errors by stable error code.",
    ["error_code"],
)
