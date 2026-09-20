# Model Serving

## Planned lifecycle

Model artifacts will be versioned and loaded before the API accepts inference traffic. Startup will validate artifact checksums, initialize each configured policy implementation, and run a small warm-up inference. `/ready` will remain unavailable if required models fail to load.

```mermaid
flowchart TD
    ArtifactStore[(Versioned artifact store)] --> Download[Startup artifact fetch]
    Download --> Checksum[Verify checksum]
    Checksum --> Load[Load tokenizer and model]
    Load --> Warmup[Warm-up inference]
    Warmup --> Ready[Mark service ready]
    Ready --> Requests[Serve inference requests]
```

The current Phase 1 implementation has no model loader. The serving lifecycle will be implemented in later phases and updated here with the selected framework, model license, versions, and measured resource use.
