# Visual retrieval integration boundary

Visual V1 retains the locked `VisualRetrievalService.search(Path | bytes, top_k)` boundary.
A separate optional `sahulat_api` HTTP adapter now implements the internal visual-only surface.
Its versioned contract, pinned OpenAPI snapshot and launch workflow are in
[Visual HTTP V1](API-VISUAL-V1.md). No authentication architecture or public gateway is implemented.
Initialize the encoder and index once per worker lifecycle and inject them into
the service. The immutable local index supports concurrent reads. GPU capacity
and request concurrency must be bounded by the hosting application; avoid one
model copy per request. Replace the service/index together when publishing a new
catalogue snapshot. Do not mutate an index in place during requests.

## Implemented internal visual contract

`POST /api/v1/search/image`: multipart `image` and integer `top_k` (default 5).
The adapter bounds bytes while streaming before multipart parsing, allows one supported
image, validates `1 <= top_k <= 100`, and calls the existing synchronous service in a
bounded worker/thread execution architecture. Uploads do not spool to disk. A future gateway
must additionally enforce limits and apply the parent's authentication,
authorization and rate limits. No separate identity system is defined here.

```json
{
  "contract_version": "visual-http-v1",
  "identity_scope": "external",
  "source_system": "<explicit-source-namespace>",
  "model": "openclip",
  "embedding_version": "<full-version-from-index>",
  "results": [
    {
      "product_id": "<catalogue-id>",
      "score": 0.0,
      "matched_image_id": "<catalogue-image-id>"
    }
  ]
}
```

The score above illustrates a schema, not a measured retrieval. The adapter uses an allowlisted
DTO and omits `ProductMatch.matched_image_path`. The IDs are explicitly external catalogue IDs,
not canonical UUIDs. The backend resolves them through the approved source namespace and
external refs before enriching with authorized catalogue fields. Recheck product
visibility there; vector membership is not authorization. Keep query bytes in
memory and do not persist uploads or log them.

Implemented mappings: invalid top_k/metadata 422, undecodable input 400, unsupported
format 415, upload too large 413, empty/unavailable index or model startup failure
503. Index/model version mismatch is a deployment error: fail readiness and expose
a generic 503. Unexpected errors remain errors, never fake empty results. Do not
expose internal exception details over HTTP. Synthetic endpoint/DB lineage tests now exercise
the adapter. Use `python -m sahulat_api` after provisioning the required pinned/offline settings.
The supplied CLI is loopback-only; parent authentication/publication/deployment remain separate.

## PostgreSQL / pgvector

The workspace now has a verified canonical PostgreSQL foundation, frozen DB-CONTRACT-V1,
Migration 001 and canonical fixture ingestion. There is still no Search schema or pgvector
adapter/extension introduced by the visual subsystem; local visual evaluation remains locked.
`VectorIndex` is the injection boundary; exact local evaluation is independent of
PostgreSQL. A future adapter must provide identity, count, and descending cosine
matches with stable image-ID ties. Insert via the parent's migration/transaction
patterns, verify extension availability, and isolate each full embedding identity.
Enforce unique image IDs within a version and vector dimension consistency.
These are future adapter considerations, not instructions to install pgvector now.

See [parallel engineering boundaries](architecture/parallel-engineering-track-v1.md) for the
proposed visual-only runtime, canonical external-ID resolution and annotation blinding.

For a pgvector cosine query, distance is ordered ascending and returned similarity
is `1 - distance`; never rank larger distance as better. Do not mix two 512-D models
simply because their dimensions match. ANN recall needs evaluation against this
exact baseline before changing the frozen benchmark. No database credentials,
schema mutations or speculative infrastructure are included in this subsystem.
