# Inference Path

## Current implementation

The Phase 2 API validates a 1–10,000 character input, runs the loaded toxicity classifier, compares its `toxic` probability to a configurable threshold, and returns the score, action, model revision, request ID, and handler latency. `/ready` remains unavailable until the model is checksum-verified and warmed up.

## Planned request lifecycle

```mermaid
sequenceDiagram
    participant C as Client
    participant A as FastAPI
    participant K as API key cache (later phase)
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
