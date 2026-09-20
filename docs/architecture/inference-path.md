# Inference Path

## Current implementation

The Phase 1 API has no inference endpoint yet. The `/ready` route becomes ready after the FastAPI startup hook completes.

## Planned request lifecycle

```mermaid
sequenceDiagram
    participant C as Client
    participant A as FastAPI
    participant K as API key cache
    participant P as Policy engine
    participant M as Local model
    C->>A: POST /v1/guardrails/evaluate
    A->>A: Validate body and assign request ID
    A->>K: Resolve tenant and project
    K-->>A: Active key context
    A->>P: Evaluate requested policies
    P->>M: Run inference
    M-->>P: Policy score
    P-->>A: Policy results and aggregate action
    A-->>C: Decision, versions, and latency
```

Raw input will not be logged by default. Later implementation phases will make the diagram match the actual request path and document failure responses.
