# Visual HTTP V1 contract

Status: versioned integration contract, `visual-http-v1`. Implemented by `sahulat_api`,
outside the locked Visual V1 core. Breaking changes require a new contract version and
reviewed OpenAPI snapshot. This is an internal development adapter, not a production security
or latency certification. No data/ML ADR, corpus or evaluation protocol is changed.

Frozen machine contract: [OpenAPI](../configs/api/visual-http-v1.openapi.json) and
[manifest](../configs/api/visual-http-v1.manifest.json). The snapshot regression checks exact
canonical bytes and SHA-256, not just endpoint names. Changes require explicit versioning/review;
never regenerate the frozen snapshot merely to silence a regression.

## Trust and ownership

The supplied CLI binds **127.0.0.1**, one worker, without access logs or trusted proxy headers.
There is no authentication implementation or CORS allowance. Do not expose this unauthenticated
adapter publicly. A later backend/gateway must enforce authentication, authorization, TLS,
rate limits, caller isolation and commercial visibility before publishing product results.
Loopback does not authenticate other local processes/users. Human query authors/judges must
not have access to runtime outputs; deploy annotation and inference in separate environments.

The runtime imports no text/evaluation/ingestion components. It neither opens PostgreSQL nor
reads `.env`, human submissions, relevance judgments, image paths from request parameters,
or remote URLs. Business writes, schema migrations, tenancy and catalogue enrichment remain
backend-owned. No fake user, category, brand, stock or currency is created.

## Lifecycle and approved assets

`create_app(HttpSettings, service_factory=...)` is the injection boundary. Its lifespan loads
one encoder/index pair per worker, in a worker thread, not at import or per request. The
default factory reuses the existing pinned encoder factory and exact `InMemoryVectorIndex`.
Required process environment:

| Setting | Meaning |
| --- | --- |
| `AI_VISUAL_INDEX_PATH` | Existing immutable catalogue `.npz`, never rebuilt on startup |
| `AI_VISUAL_INDEX_SHA256` | Lowercase SHA-256 of exact index file bytes |
| `AI_VISUAL_SOURCE_SYSTEM` | Explicit namespace; must match index `metadata.dataset_version` |
| `HF_HUB_OFFLINE=1` | Existing model assets must already be provisioned in the cache |
| Existing `VISUAL_*` | Locked model/device/cache settings; process environment, not `.env` loading |
| `AI_MAX_CONCURRENT_REQUESTS` | Positive simultaneous body/parse/inference admissions; default 1 |
| `AI_BODY_TIMEOUT_SECONDS` | Total upload deadline; default 15 seconds, maximum 300 |

The host controls asset provisioning and read-only storage. Keep the pinned file immutable
through startup and serve a replacement app/service on a new deployment; no hot mutation or
live reload is implemented. Model/index identity, nonempty catalogue, namespace and the locked
image policy must agree. Startup failure leaves liveness up but readiness/inference at 503;
no automatic fallback or model reselection occurs. Shutdown releases the app's service reference.
Each additional worker would hold another model/index copy; the supplied CLI starts only one.

Lifecycle follows [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/), and synchronous
parsing/model work is kept outside the event loop. Model work cannot be forcibly terminated
by cancelling an HTTP task: its admission slot stays held until the worker actually completes.
No unbounded waiting request queue is introduced. Host-level resource limits and a model-hang
watchdog remain deployment concerns; a stuck model must not be treated as an empty result.

## HTTP surface

- `GET /health/live`: 200 `{"status":"live"}`; process liveness, not model availability.
- `GET /health/ready`: 200 ready/contract version, or generic 503 if initialization failed or
  an index-compatibility error subsequently invalidated the service. Busy is not unready.
- `POST /api/v1/search/image`: exactly one multipart file `image`, optional text `top_k`.
- `GET /openapi.json`: machine contract. Interactive `/docs` and `/redoc` are disabled.

No text, voice, RAG, business CRUD, metrics runner or retrieval-evaluation route exists.

### Request limits and rendering

`top_k` defaults to 5; accepts ASCII decimal digits representing integers 1 through 100.
No trimming, synonym expansion or query normalization. Unknown/duplicate multipart fields,
multiple images, a file-valued `top_k`, URL query parameters and transfer encodings are rejected.
Only multipart/form-data, no compressed HTTP body. Client filenames are ignored and never
used as storage paths. PNG/JPEG/WebP MIME must agree with decoded image format.

The complete request is bounded while streaming **before** multipart parsing, including
chunked requests without Content-Length. Total limit: 20 MiB + 64 KiB multipart overhead.
Declared lengths must be valid and equal the received length. Image part: at most 20 MiB;
top_k: at most 32 bytes; at most two parts/four headers per part; each header at most 4096 bytes;
boundary length 1..70 printable ASCII bytes. Explicit multipart completion is required.

Parsing uses bounded bytearrays and [Python Multipart callbacks](https://multipart.fastapiexpert.com/api/),
not a disk-spooling UploadFile. Uploads stay in memory; they are not persisted or logged.
The locked Visual V1 policy additionally rejects unsafe/truncated/animated images, sides below
16 or above 12,000, over 25,000,000 pixels, and decompression bombs. Dimension/animation/decode
failures are generic 400. These are safety bounds, not a search-performance pass criterion.

### Response and identity

Top-level allowlist: `contract_version`, `identity_scope`, `source_system`, `model`,
`embedding_version`, `results`. Each result contains only `product_id`, finite cosine `score`
and `matched_image_id`. **`identity_scope` is always `external`: IDs are catalogue/external
references, NOT canonical PostgreSQL UUIDs**, even if their strings happen to look like UUIDs.
No filename, `ProductMatch.matched_image_path`, local path, vendor or commercial metadata
is returned. Successful responses and expected failures use Cache-Control: no-store.

The unchanged `VisualRetrievalService` owns MAX aggregation, unique product results, full
identity matching, stable score/product/image ties and top-k neighbor expansion. This adapter
does not reorder, filter, fuse or enrich its results. Fewer than top_k results are possible
when the indexed catalogue contains fewer unique products.

For canonical integration, the backend explicitly resolves:

```text
(source_system, external_product_id) -> catalog.product_external_refs -> Product UUID
(source_system, external_image_id)   -> catalog.image_external_refs -> Image UUID
                                                               -> product_images.product_id
```

`catalogue.load_external_image_references(config, source_system)` is an optional read-only
projection for a backend-supplied DB context, not a runtime request dependency. It returns
only identities, no source paths. `identity.resolve_canonical_matches(...)` consumes that
projection, preserves input ranking/scores, verifies image/product association and rejects
missing, duplicate, ambiguous, cross-namespace or conflicting lineage rather than silently
dropping/relabeling results. Neither helper grants permissions. The backend must still recheck
visibility, authorization and canonical record state; mapping is not publication eligibility.
Khaadi draft listings remain draft, currency NULL, unknown stock untouched.

### Safe failures

Error shape: `{"error":{"code":"<stable-code>","message":"<safe-message>"}}`.
No internal exception text, tracebacks, secrets, upload bytes or local paths in responses/logs.

| HTTP | Meaning |
| --- | --- |
| 400 | Malformed/truncated multipart, bad lengths or unsafe/undecodable image |
| 408 | Upload timed out/disconnected |
| 413 | Total request or image-part byte limit exceeded |
| 415 | Unsupported request/image encoding or format/MIME mismatch |
| 422 | Missing/unknown/duplicate fields, invalid top_k or wrong field type |
| 500 | Unexpected service failure; never fabricated empty results |
| 503 | Startup/index failure, incompatible identity, or bounded admission busy |

Busy is `visual_busy`; unavailable is `visual_unavailable`. Startup/runtime failures log only
event name and exception class, not its message. Parent logging/tracing must preserve this
redaction and must not capture bodies. No automatic audit/outbox events or DB triggers are added.

## Local launch

Install optional HTTP/test extras with the existing dependency versions (ML assets are separately
provisioned; no model weights or annotation data belong in the HTTP dependency list):

```powershell
python -m pip install -r requirements-api-v1.txt
python -m pip install -e '.[api,api-test,dev]'
$env:AI_VISUAL_INDEX_PATH='artifacts/catalogue-openclip.npz'
$env:AI_VISUAL_INDEX_SHA256=(Get-FileHash -Algorithm SHA256 -LiteralPath $env:AI_VISUAL_INDEX_PATH).Hash.ToLowerInvariant()
$env:AI_VISUAL_SOURCE_SYSTEM='khaadi-v1'
$env:HF_HUB_OFFLINE='1'
$env:VISUAL_DEVICE='cpu'
python -m sahulat_api --port 8000
# Separate terminal: curl.exe http://127.0.0.1:8000/health/ready
```

The hash command measures a trusted existing asset; it is not permission to accept an arbitrary
unreviewed index. Provision compatible cached models with the existing ML tooling beforehand.
No PostgreSQL password/URL, role redesign or model download is required by HTTP startup.
