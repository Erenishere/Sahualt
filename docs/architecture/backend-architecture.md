# Backend architecture

Clean-ish layering:

- `SahulatAI.Api` — HTTP, middleware, DI composition
- `SahulatAI.Application` — use cases / features
- `SahulatAI.Domain` — entities and domain rules
- `SahulatAI.Infrastructure` — EF Core, Redis, identity, ML HTTP clients

Search features delegate inference to ML; ranking fusion for official benchmarks remains ML-side until product requirements say otherwise.
