# Visual Integration Bridge V1

Owner: Adeel's isolated ML/integration workstream. Version: `visual-integration-bridge-v1`.
Gate status: **GREEN after CATALOG-READER-ACCESS-V1**.
The client, cached OpenCLIP HTTP path and scoped live canonical resolution are verified.
Access provisioning is isolated in [CATALOG-READER-ACCESS-V1](CATALOG-READER-ACCESS-V1.md).

## Purpose and boundary

This checkout-local Python harness proves an application-side visual integration boundary,
not the production backend. There is no existing ASP.NET infrastructure project to extend.
Typed immutable wire models and the existing JSON/multipart contract are consumable by a future
.NET client, but no .NET implementation or interoperability build is claimed here. No new
dependencies, backend architecture, migrations or API operations were introduced.

```text
Application-side harness
  -> VisualAIClient (loopback HTTP, API-VISUAL-V1)
  -> Existing OpenCLIP visual service (unchanged exact cosine / product MAX ranking)
  -> Ranked EXTERNAL product/image identities and raw cosine scores
  -> ReadOnlyCatalogue (scoped PostgreSQL snapshot)
  -> Existing resolve_canonical_matches helper
  -> Ordered canonical UUIDs + minimal VerifiedProduct
```

FastAPI owns intelligence and retrieval output only. PostgreSQL remains the business-data source
of truth. Resolution is not authentication, authorization, publication eligibility or a business
API. Draft fixture products may be verified internally; their listings remain draft and are not
published by this harness.

## Existing visual API contract

Authority: [API-VISUAL-V1](API-VISUAL-V1.md), contract version `visual-http-v1` and its unchanged
[OpenAPI snapshot](../configs/api/visual-http-v1.openapi.json).

Only these operations are called:

- `GET /health/live`: exact liveness mapping.
- `GET /health/ready`: exact readiness/version mapping; unavailable is not an empty ranking.
- `POST /api/v1/search/image`: one original image byte sequence plus `top_k` in multipart.

The caller accepts only a literal loopback HTTP address, such as `http://127.0.0.1:8000` or
`http://[::1]:8000`. DNS hostnames, credentials in URLs, non-root URL paths, redirects, environment
proxies and remote hosts are rejected. This does not authenticate local processes. Keep runtime
outputs separate from human query/labeling work; no annotation infrastructure is accessed.

Uploads remain memory-only: no persistence, re-encoding, alternate preprocessing or second model
pipeline. JPEG/PNG/WebP and the existing 20 MiB image / 20 MiB + 64 KiB body limits apply.
`top_k` is an integer from 1 to 100. Server-side decoding/safety checks remain server-owned.
Successful response bodies are bounded to 256 KiB, JSON-only and uncompressed. Duplicate JSON
keys, nonfinite scores, unexpected fields and incompatible namespace/version/model are rejected.
OpenCLIP and the expected embedding version are pinned by caller configuration, not selected
from response content.

Frozen response fields are `contract_version`, `identity_scope`, `source_system`, `model`,
`embedding_version`, `results`. Each match has only external `product_id`, `matched_image_id`
and `score`. The typed client adds rank as the 1-based response position; it does not invent
business fields. Image IDs such as `ACA231001/image_0.jpg` remain opaque relative identities,
never filesystem instructions. Even a UUID-shaped external ID must resolve through external refs.

## Canonical resolution and ranking

`ReadOnlyCatalogue` reads requested identities through the purpose-specific
`catalog.visual_product_resolution_v1` view. Its underlying authoritative relationships are:

```text
(source_system, external_product_id)
  -> catalog.product_external_refs -> catalog.products
(source_system, external_image_id)
  -> catalog.image_external_refs -> catalog.product_images
  -> product_images.product_id must equal the resolved products.id
```

The minimal business projection is immutable `VerifiedProduct(product_id, name, description)`.
No Listing, Inventory, Variant, vendor, image path or commercial projection is joined.
Archived products/images and missing required product semantics fail closed. Missing, malformed,
unknown, cross-product, out-of-namespace or ambiguous lineage returns a stable internal failure.
There is no guessing, creation, partial-result filtering or repair.

The existing `sahulat_api.identity.resolve_canonical_matches` owns canonical lineage validation.
The consumer preserves response position and numeric cosine scores exactly. It validates the
frozen descending score / external-product tie order without sorting. Resolution cannot change
rank, score or external identity, and duplicate canonical products are rejected. Canonical UUID
order is not used for ranking. MAX aggregation and image tie decisions remain Visual V1-owned.

## Read-only PostgreSQL boundary

The bridge reuses `DatabaseConfig` and existing configuration conventions, but exposes no general
SQL execution API. A short-lived asynchronous `psql` process supports native cancellation and
deadlines without modifying the shared synchronous repository helpers. SQL is private, bounded
to top-k identities and safely quotes literals with standard-conforming strings enabled.

Before reading business data, the same repeatable-read, read-only transaction checks effective
permissions. The separately provisioned `sahulat_visual_reader` credential must:

- Be a non-superuser without role/database creation, replication or RLS bypass privileges.
- Have catalog usage and SELECT only on `catalog.visual_product_resolution_v1`, without grant option.
- Have no CREATE/TEMPORARY on the database or CREATE on application/public schemas.
- Have no business-table write, REFERENCES or TRIGGER privileges, including inherited or
  column-level privileges; no SELECT on base tables or unrelated application objects is accepted.
- Have no role memberships that could permit elevated role assumption.

The bridge itself never grants access. Its separate access gate adds one scoped role/view via a
versioned provisioning artifact. `postgres` remains rejected before launching a database process.
Broad reader roles are not a substitute for scoped credentials.

`default_transaction_read_only=on`, `BEGIN ... READ ONLY`, a 10-second SQL timeout, 3-second lock
timeout, 5-second connect timeout and 15-second overall database deadline protect the read.
Cancellation/timeout terminates the process; errors discard stderr. The password is supplied only
through the subprocess environment, never SQL, command arguments, logs, CLI output or reports.
No outbox/audit events, imports, DDL or business writes are performed.

The initial diagnostic found only the `postgres` superuser, which blocked the original bridge
gate. CATALOG-READER-ACCESS-V1 now provisions its approved runtime reader without editing the
frozen [DB-CONTRACT-V1](DB-CONTRACT-V1.md). The real reader-backed smoke resolves five canonical
Products with unchanged order/scores. Administrative diagnostics and temporary-DB guard tests
remain distinct from this successful live application-role smoke.

## Failure model

`BridgeError` carries only a deterministic code. Upstream exception messages, API error messages,
database stderr, connection secrets, filesystem paths and stack traces are not exposed by the
CLI. Cancellation remains native `asyncio.CancelledError`; the CLI emits `cancelled` with exit
130. Validation/service failures exit 2; success exits 0.

| Boundary | Representative codes |
| --- | --- |
| Configuration/input | `invalid_configuration`, `invalid_image`, `invalid_top_k`, `upload_too_large`, `unsupported_image` |
| HTTP/service | `api_unavailable`, `model_not_ready`, `api_busy`, `api_timeout`, `api_failure`, `image_request_rejected` |
| Contract | `malformed_response`, `contract_mismatch`, `scope_mismatch`, `model_identity_mismatch`, `invalid_identity` |
| Database/catalog | `database_permission_rejected`, `database_unavailable`, `database_timeout`, `catalog_state_invalid`, `canonical_resolution_failure`, `ambiguous_identity` |
| Invariant | `ranking_violation` |

The HTTP overall deadline defaults to 30 seconds per operation, including response streaming.
No implicit retries or fallback models can hide unavailable state or repeat uploads.

## Run from the checkout root

Use the existing environment with API/API-test/ML dependencies and cached model assets.
The isolated `integration` namespace is not installed as a shared application package. Supply an
explicit credential-file location approved by the database owner; do not pass a password on the
command line. A missing file fails closed. Existing DATABASE_* environment variables take
precedence over the file, so use a dedicated process/environment without administrative overrides.
Do not alter the shared `.env` for this task.

After the existing internal visual API has been started using its documented launcher:

```powershell
python -m integration.visual_bridge_v1 `
  --api-url http://127.0.0.1:8000 `
  --source-system khaadi-v1 `
  --embedding-version openclip-vit-b32-1a25a446712b-af731563a693-v1 `
  --database-env 'PATH_TO_APPROVED_READER_ENV' `
  --image 'PATH_TO_TEST_IMAGE.png' --mime-type image/png --top-k 5
```

The CLI reports rank, canonical product/image UUIDs and original score only; product text remains
available on the typed internal result, not a new HTTP/business response.

Manual cached-model smoke (starts the existing app on an ephemeral **loopback-only** port):

```powershell
$env:HF_HUB_OFFLINE='1'
$env:VISUAL_DEVICE='cpu'
python -m integration.visual_bridge_v1.smoke `
  --index artifacts/catalogue-openclip.npz `
  --index-sha256 cd6c6d6e53f7f7ad94de3f555cca71685e5905d50eb36f54d7c87308e0a1084b `
  --source-system khaadi-v1 `
  --database-env 'PATH_TO_APPROVED_READER_ENV'
```

Use `.env.visual-reader` provisioned by the access gate for `PATH_TO_APPROVED_READER_ENV`.
Without reader configuration, this reports the HTTP smoke separately and remains RED. The
administrative `.env` remains rejected, not used for catalog resolution. The smoke uses one
synthetic 32x32 PNG, existing cached OpenCLIP and the existing index. It is not benchmark evidence,
does not download/rebuild assets and makes no search-quality claim.

Verification commands:

```powershell
$env:RUN_DATABASE_TESTS='1'
python -m pytest tests/visual_bridge_v1 -q
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m mypy integration
python -m pip check
```

## Team boundary and stopping point

The original bridge and its tests remain isolated under `integration/visual_bridge_v1`.
The access follow-up adds an isolated forward provisioning artifact and its own docs/tests;
it changes no shared Migration 001, Visual API/core, contracts, frozen data, text-query,
labeling, evaluation, ingestion or teammate-owned backend-readiness modules.

No authentication, IAM workflows, catalog CRUD, production gateway, frontend, Commerce, voice,
RAG, text retrieval, FTS, BM25, dense text, RRF, embeddings, pgvector, Redis, Celery, Docker or
public deployment is implemented. No queries, judgments or adjudications are produced. Future
product publication and permission checks belong to the application/backend owner, not this
harness. Stop here: the scoped reader and live canonical smoke are now verified.

Operational references: [HTTPX async client](https://www.python-httpx.org/async/),
[HTTPX timeouts](https://www.python-httpx.org/advanced/timeouts/),
[PostgreSQL transaction characteristics](https://www.postgresql.org/docs/18/sql-set-transaction.html).
