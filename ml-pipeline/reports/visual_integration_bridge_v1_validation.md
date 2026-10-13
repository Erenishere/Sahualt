# Visual Integration Bridge V1 validation

Date: 2026-09-12. Owner: Adeel's ML/integration workstream.
Historical initial gate: **RED / blocked on an approved read-only PostgreSQL credential**.

## Access-gate follow-up

Current gate: **GREEN** after [CATALOG-READER-ACCESS-V1 validation](catalog_reader_access_v1_validation.md).
The scoped `sahulat_visual_reader` now selects only the minimal Catalog resolution view, not
base tables. Live cached OpenCLIP -> unchanged loopback API -> bridge -> PostgreSQL resolution
returns five canonical Products with unchanged order/scores and zero business writes.
Administrative credentials remain rejected. The original results below are retained as
historical evidence of why the bridge correctly stopped before access was approved; they are
not the current live-resolution status.

## Verified scope and acceptance boundary

Added an isolated, strongly typed Python application-side harness, not an ASP.NET backend:

```text
VisualAIClient -> unchanged internal API-VISUAL-V1 -> ranked external identities
  -> scoped read-only PostgreSQL snapshot -> existing canonical-resolution helper
  -> ordered canonical UUIDs / original scores / minimal VerifiedProduct
```

The client, failure handling, ranking invariants, synthetic canonical resolution and PostgreSQL
permission-rejection diagnostic are VERIFIED. Actual cached OpenCLIP over loopback HTTP is
VERIFIED. **Live application-role PostgreSQL canonical resolution is NOT VERIFIED**. A passing
HTTP smoke or synthetic snapshot is not evidence of the missing live database boundary.

The read-only administrative role diagnostic found only `postgres`, a superuser. No suitable
runtime reader exists. [DB-CONTRACT-V1](../docs/DB-CONTRACT-V1.md) reserves that identity for
administration and leaves reader provisioning to the schema owner. The bridge rejects it before
opening an application database connection. No new role, grant, migration, authentication flow
or teammate-owned readiness module was created to bypass this gate constraint.

## Implementation

- Exact liveness/readiness/search wire mappings; explicit caller-pinned source namespace,
  OpenCLIP model and embedding version. Frozen response fields remain unchanged.
- Loopback-literal HTTP only; no proxy inheritance, redirects, public exposure or gateway.
- Original image bytes in bounded memory-only multipart; no preprocessing/re-encoding or files
  written. Existing MIME, top-k and upload policy reused.
- Bounded JSON response, duplicate-key/nonfinite rejection, exact field allowlists, safe status
  mappings, timeouts and native cancellation. No upstream messages or database stderr exposed.
- Scoped Product/Image external-reference joins; image must belong to resolved Product.
  External IDs are never canonical aliases, even when UUID-shaped.
- Existing `resolve_canonical_matches` reused. Rank and numeric scores preserved; no filtering,
  sorting, business ranking or aggregation changes. Ambiguous/unknown/malformed lineage fails.
- Minimal immutable product projection: canonical UUID, Name, Description. No Listing/Inventory
  reads, commercial state, permissions workflow or general catalog service.
- Private read-only repeatable-read SQL with effective permission checks, connection/statement/
  lock/overall deadlines and cancellable subprocess ownership. No business writes or events.
- Explicit credential-file entry point; missing file fails rather than silently using shared
  administrative configuration. Credentials are not printed or written to reports.

No existing files were edited. Shared ML, Visual API, frozen protocols, Gate 1/ingestion evidence,
database contract, teammate text/labeling/FTS modules and shared app ownership remain unchanged.
Import-boundary regression rejects any `sahulat_text` dependency in the bridge.

## Contract and asset preservation

Contract: [API-VISUAL-V1](../docs/API-VISUAL-V1.md), `visual-http-v1`.
Measured unchanged OpenAPI SHA-256:
`9c6fe17c1fd69190734b47351fe148cf85ac8ae1999df59e4a2b8493718e00a9`.

Existing cached index: `artifacts/catalogue-openclip.npz`, 2,093 vectors.
Exact file SHA-256:
`cd6c6d6e53f7f7ad94de3f555cca71685e5905d50eb36f54d7c87308e0a1084b`.
Namespace: `khaadi-v1`.
Embedding version: `openclip-vit-b32-1a25a446712b-af731563a693-v1`.

No encoder selection, FashionCLIP/OpenCLIP behavior, cosine normalization, MAX product aggregation,
tie policy or EVAL-VISUAL-V1 semantics changed. Existing query-image encoding is exercised by the
smoke; no stored embeddings, catalogue rebuild, model download or benchmark results are produced.

## Tests and static checks executed

Python runtime: 3.12.10. PostgreSQL tests explicitly enabled with `RUN_DATABASE_TESTS=1`.

| Verification | Measured result |
| --- | --- |
| New bridge tests | 98 passed, included in combined adapter and full runs |
| Bridge + existing API directory | 174 passed (98 bridge + 76 API) |
| Database-marked suite | 59 passed, 446 deselected; includes two new bridge guard diagnostics |
| Existing `tests/database` directory | 59 collected and all passed in the full run; two are unit checks rather than database-marked tests |
| Full repository | 503 passed, 2 opt-in model tests skipped, 0 failures; 66.85 seconds |
| Ruff lint | PASS, whole repository |
| Ruff format check | PASS, 128 Python files |
| mypy existing source | PASS, 72 source files |
| mypy isolated integration | PASS, 10 source files |
| Dependency validation | PASS, `pip check`: no broken requirements |
| Both CLI help commands | PASS |
| .NET build/format | Not applicable: no .NET code/project introduced |

Two existing upstream deprecation warnings remain: Starlette TestClient's HTTPX integration and
the AnyIO BlockingPortal alias. They were not hidden, removed or worked around by changing pins.
The two opt-in pretrained-model tests remain skipped by their existing policy; the manual real
cached OpenCLIP smoke below was separately executed.

New synthetic coverage includes health/readiness, unchanged image bytes, safe API errors,
unavailable/busy/not-ready states, timeouts/cancellation, malformed JSON/headers, response/input
bounds, invalid fields/scores/identities, namespace/model mismatch, unknown UUID-shaped external
identity, duplicate/cross-product lineage, archived or malformed catalog state, read-only transport,
permission rejection, process cancellation, CLI safe errors and no reranking or score changes.
Synthetic fixtures are not benchmark evidence or genuine human queries.

## Cached OpenCLIP integration smoke

Executed the new smoke module twice with `HF_HUB_OFFLINE=1`, CPU and the pinned existing index.
It launched the unchanged FastAPI app using Uvicorn on an ephemeral literal loopback address,
one worker, access logs off and untrusted proxy headers. A synthetic 32x32 PNG was sent unchanged
by the typed application client. Liveness/readiness/search succeeded and five products returned.

Measured safe output:

```json
{
  "api_ranked_products": 5,
  "api_smoke": "PASSED",
  "blocker": "database_permission_rejected",
  "bridge_version": "visual-integration-bridge-v1",
  "catalog_writes": 0,
  "gate": "RED",
  "live_canonical_resolution": "NOT_VERIFIED",
  "resolved_products": 0,
  "source_system": "khaadi-v1"
}
```

This is observational integration evidence, not retrieval quality/SLO certification or public
deployment. The administrative `.env` was supplied only to prove the application's early
rejection; it was never accepted for application-role catalog resolution. The database guard
test compiled the metadata check and exercised its rejected branch in an isolated migrated test
database. The positive reader/business-query branch remains unverified against a live approved
reader; no claim of full OpenCLIP-to-canonical-DB end-to-end success is made.

## Live database preservation

A separate **read-only administrative diagnostic**, not the application bridge, measured:

| State | Count/value |
| --- | --- |
| Server/database | PostgreSQL 18.6 / `sahulat_ai_dev` |
| Non-system roles | Only `postgres`, superuser |
| Products | 400 |
| Unarchived default variants | 400 |
| Draft listings | 400 |
| Product images | 2,093 |
| Product external refs | 400 |
| Image external refs | 2,093 |
| Inventory / outbox / audit rows | 0 / 0 / 0 |
| Invented Brand/Category/Size/Currency fields | 0 |
| Search/Commerce/Analytics schemas | 0 |
| pgvector extension | 0 |
| tsvector/tsquery columns | 0 |

No fixture record or schema was altered, no stock inferred and no production event emitted.
Existing regression tests use only their generated temporary databases, not business-data writes
to `sahulat_ai_dev`. No new test/application account was provisioned.

## Complete file inventory

Added (18 files):

- `integration/__init__.py`
- `integration/visual_bridge_v1/__init__.py`
- `integration/visual_bridge_v1/__main__.py`
- `integration/visual_bridge_v1/errors.py`
- `integration/visual_bridge_v1/models.py`
- `integration/visual_bridge_v1/client.py`
- `integration/visual_bridge_v1/catalogue.py`
- `integration/visual_bridge_v1/bridge.py`
- `integration/visual_bridge_v1/cli.py`
- `integration/visual_bridge_v1/smoke.py`
- `tests/visual_bridge_v1/__init__.py`
- `tests/visual_bridge_v1/test_client.py`
- `tests/visual_bridge_v1/test_catalogue.py`
- `tests/visual_bridge_v1/test_bridge.py`
- `tests/visual_bridge_v1/test_database_guards.py`
- `tests/visual_bridge_v1/test_cli.py`
- `docs/VISUAL-INTEGRATION-BRIDGE-V1.md`
- `reports/visual_integration_bridge_v1_validation.md`

Modified existing files: **none**. No dependencies added or upgraded; no `.env`, shared entry
point, project manifest, CI, contract snapshot or team-owned documentation was changed.
The checkout has no Git metadata, so review used the explicit new-file inventory/source checks
and frozen contract hash rather than claiming an unavailable `git diff`. No init/commit/push.
Generated Python/test caches are already ignored and are not implementation artifacts.

## Blocker, non-overlap and stop

To finish this gate, the database/schema owner must supply an approved, scoped non-superuser
reader credential location/setup reference. No password should be supplied in chat. Then rerun
the existing documented smoke with that configuration and require actual canonical products,
unchanged ranking and `live_canonical_resolution=VERIFIED` before changing the gate to GREEN.
No role redesign/provisioning or another team member's backend module is taken over here.

No text retrieval, PostgreSQL FTS, BM25, dense text, RRF, human query authoring, labeling,
judgments/adjudication, authentication, IAM flows, Commerce, offers, frontend, voice, RAG,
vendor workflows, Redis/Celery, orchestration or public deployment was implemented. No human
queries or relevance labels were fabricated. No new retriever, Search infrastructure or stored
embedding/vector infrastructure was created. Stop at the isolated bridge and report the live
reader limitation; do not continue into another gate.
