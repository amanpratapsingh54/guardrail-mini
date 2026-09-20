# Security notes

## API keys and secrets

API keys contain 256 bits of random material. PostgreSQL stores their SHA-256 hashes and non-secret prefixes; the plaintext is returned once when a key is created. Use a separate key for each project and rotate or revoke it if exposed. Do not commit `.env`; it is ignored by Git. Copy `.env.example` for local setup and replace its example values locally.

The application never logs request bodies, query parameters, bearer headers, free-form log messages, or detected PII values. JSON logs use a fixed field allowlist. Error responses also avoid echoing validation input or exception text.

## Request limits

HTTP request bodies are capped at 65,536 bytes by default. Set `GUARDRAIL_MAX_REQUEST_BODY_BYTES` between 1,024 and 1,048,576 when the API needs a different bound. Evaluation text is separately limited to 10,000 characters. Authenticated projects are limited to 600 evaluation requests per 60-second process-local window by default; set `GUARDRAIL_RATE_LIMIT_REQUESTS_PER_MINUTE` to tune it.

The rate limiter is in-process and intentionally bounded. Each API process maintains its own window, so multiple replicas do not share a global quota. Put a gateway with a shared rate-limit policy in front of a multi-replica deployment if a strict aggregate quota is required.

## Network and browser access

CORS is disabled. The API does not send cross-origin browser permissions by default. Same-origin server applications can call it directly. If a browser client is needed, configure a specific trusted-origin allowlist at the HTTPS gateway; do not allow every origin with credentialed requests.

The local default bind address is `127.0.0.1`. For deployment, terminate HTTPS at a managed ingress or reverse proxy, keep the API and database on a private network, and use managed secret storage or workload identity for credentials. Do not expose PostgreSQL, object-store administration ports, or the unauthenticated Prometheus metrics endpoint to the public internet.

## Model and policy limits

Toxicity and prompt-injection classifiers can produce false positives and false negatives. They are screening components, not a complete security boundary. Review thresholds, allow/block thresholds, and the returned policy results should be validated on representative data before use in a consequential workflow. The PII detector is English-focused and US-identifier-focused for several recognizers.

## Dependency checks

Install the development extras and run the dependency audit from the repository root:

```bash
python -m pip install -e ".[dev,ml,pii]"
pip-audit
```

The audit needs access to the Python advisory service. Review the package, affected versions, and fix availability before changing pins; do not suppress findings without documenting why.
