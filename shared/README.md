# Shared contracts

Non-executable cross-layer artifacts only.

- `api-contracts/backend/` — OpenAPI or JSON schemas for the ASP.NET public API (future).
- `api-contracts/ml/` — Copied/versioned ML service OpenAPI manifests (source of truth remains `ml-pipeline/configs/api/` until promoted).
- `schemas/` — Shared JSON Schema or event payloads agreed by frontend/backend/ML.

Do not place application business logic here.
