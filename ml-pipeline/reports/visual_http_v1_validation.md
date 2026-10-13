# Visual-only HTTP integration V1 validation

Date: 2026-09-12. Gate: **GREEN for the internal development adapter**. This is not a
production security/SLO certification, deployment claim or new retrieval benchmark.

## Scope and authoritative boundaries

The separate optional `sahulat_api` package reuses locked `VisualRetrievalService`, encoder
factory, exact index and image policy. No Visual V1 core source, aggregation, tie behavior,
encoder selection, evaluation protocol or prior benchmark evidence was modified.
ADR-DATA-001, DB-CONTRACT-V1, canonical ingestion and ADR-ML-004 remain unchanged.

Implemented: health/readiness, image-only multipart endpoint, bounded memory-only parsing,
once-per-worker lifecycle, safe errors, pinned/offline startup, explicit external identities,
optional read-only canonical lineage projection/resolution and synthetic tests. No public
authentication system, gateway, business CRUD, deployment/containerization, voice or RAG.

## Versioned HTTP contract

- Contract: `visual-http-v1`; [contract](../docs/API-VISUAL-V1.md).
- Frozen [OpenAPI](../configs/api/visual-http-v1.openapi.json) and
  [manifest](../configs/api/visual-http-v1.manifest.json).
- Exact OpenAPI SHA-256:
  `9c6fe17c1fd69190734b47351fe148cf85ac8ae1999df59e4a2b8493718e00a9`.
- Regression checks compare canonical snapshot bytes and SHA-256 against actual `create_app()`.
- Identity is explicitly `external`, with source namespace; catalogue IDs are never silently
  relabeled canonical UUIDs. Backend helpers resolve joined product/image external references,
  preserve scores/order and fail on missing/conflicting/cross-product lineage. Resolution does
  not grant authorization or commercial eligibility.
- Public DTO allowlist excludes `matched_image_path`, filenames, source paths, commercial
  fields and other product metadata.

Requests: JPEG/PNG/WebP, MIME/decode agreement, one image, ASCII decimal top_k 1..100/default5.
Duplicate/unknown fields, URL query parameters and unsupported encodings rejected. Complete
body bounded before parsing: 20 MiB + 64 KiB; image 20 MiB; upload deadline default15 seconds;
default one simultaneous body/parse/model admission. Cancelled requests retain model occupancy
until the worker actually finishes. No unbounded waiting queue, disk spool or upload persistence.

## Verification executed

```powershell
$env:RUN_DATABASE_TESTS='1'
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m pip check
python scripts/freeze_text_query_tooling.py --verify-only
python scripts/prepare_text_evaluation.py verify
python scripts/prepare_text_evaluation.py query-status
```

| Check | Executed result |
| --- | --- |
| Full repository regression | **405 passed**, 2 opt-in pretrained-model tests skipped; 43.71 seconds |
| New HTTP/identity/contract/lifecycle tests | 76 passed within the full suite |
| New PostgreSQL canonical identity tests | 3 passed, isolated temporary DB after Migration 001 |
| All DB regression tests | 59 passed within the full suite (previous56 + new3) |
| Prior text/fixture/query/corpus/Visual V1 tests | Remain green within the full suite |
| Ruff lint | Passed |
| Formatting | Passed, 112 Python files already formatted |
| mypy | Passed, 72 source files |
| Installed dependency consistency | Passed, no broken requirements |
| Frozen query-tooling snapshot | Verified GREEN, original content-addressed snapshot preserved |
| EVAL-TEXT-V1/corpus verification | GREEN; genuine human queries/labels still pending |

Coverage includes safe startup/model/index faults, namespace/SHA drift, supported/bad/spoofed/
oversized images, decompression bombs, malformed/truncated multipart, header limits, missing/
duplicate/unknown/wrongly typed parts, invalid top_k, chunked body bounds, declared-length
mismatch, timeout/overload/cancellation, once-only initialization/cleanup, non-persistence,
safe failure redaction, absence of text/business routes/imports and frozen OpenAPI bytes.
Tests are synthetic engineering fixtures, not benchmark queries, relevance labels or scores.

Two non-failing upstream deprecation warnings were visible, not suppressed: Starlette's
httpx TestClient compatibility and its anyio BlockingPortal alias. Current pinned behavior
passes; future dependency/test-client migration requires separate compatibility review.

## Cached real-model smoke

Executed a separate process with `HF_HUB_OFFLINE=1`, CPU, the existing approved OpenCLIP cache
and `artifacts/catalogue-openclip.npz` (2,093 existing vectors). Initialized the actual lifespan,
checked liveness/readiness and posted one synthetic 32x32 PNG. Liveness200, readiness200,
image endpoint200, five product results. No output scores/IDs are claimed as benchmark evidence.
This smoke used the existing visual model's normal query encoding; no catalogue embedding
artifact was generated, index rebuilt, model downloaded/reselected or evaluation run.

Pinned existing index file SHA-256:
`cd6c6d6e53f7f7ad94de3f555cca71685e5905d50eb36f54d7c87308e0a1084b`.
The smoke was in-process HTTP testing, not a public Uvicorn deployment/SLO test. The launch
entry point was verified with `python -m sahulat_api --help` and a synthetic CLI unit test
that asserts loopback, one worker, access logs off and proxy headers untrusted.

## Live data and forbidden infrastructure

A read-only PostgreSQL catalogue check measured `sahulat_ai_dev`, server18.6, products400,
images2,093, inventory0 and outbox_events0. Search/Commerce/Analytics schemas0, vector
extension0 and tsvector/tsquery columns0. Existing fixture data was not imported, updated,
activated or replaced. New DB tests created/dropped only their isolated generated test DBs.
No application/migration role was added. The HTTP runtime itself uses no DB credentials;
the optional read-only backend helper takes the caller's explicit config.

No Search schema/tables, PostgreSQL FTS/tsquery/ranking/GIN, BM25, pgvector, new stored
embeddings, dense encoder, RRF, fusion, Commerce, fake metadata, queries or relevance labels
were created. The existing visual service was wrapped, not a new retriever implemented.

## Human research state and freeze preservation

PRODUCT-TEXT-V1: 400 documents; SHA-256
`5067202e69fbe0dfd61601e23cfe037a88fcc39a533c923dbdab270e0208e43f`.
EVAL-TEXT-V1 remains frozen and verified. Genuine human queries0, coverage requirements not
met; human dataset PENDING and query dataset freeze NOT POSSIBLE. Text retrieval remains
blocked. PostgreSQL FTS is still the approved future lexical baseline; BM25 is not approved.

The original TEXT-QUERY-V1 software snapshot verifies unchanged. Adding optional HTTP extras
intentionally changes the working pyproject.toml; do not claim `--check-working-tree` matches
the old snapshot. Default immutable-snapshot verification remains GREEN. No original snapshot,
query schema, protocol lock, frozen corpus, annotation data or status artifact was overwritten.

## Complete file inventory

Added:

- `src/sahulat_api/__init__.py`
- `src/sahulat_api/__main__.py`
- `src/sahulat_api/app.py`
- `src/sahulat_api/settings.py`
- `src/sahulat_api/uploads.py`
- `src/sahulat_api/identity.py`
- `src/sahulat_api/catalogue.py`
- `src/sahulat_api/cli.py`
- `tests/api/test_visual_http.py`
- `tests/api/test_identity.py`
- `tests/api/test_lifecycle.py`
- `tests/api/test_contract_snapshot.py`
- `tests/database/test_visual_identity.py`
- `configs/api/visual-http-v1.openapi.json`
- `configs/api/visual-http-v1.manifest.json`
- `requirements-api-v1.txt`
- `docs/API-VISUAL-V1.md`
- `reports/visual_http_v1_validation.md`

Modified:

- `pyproject.toml`: optional HTTP/test extras, launch entry point, API type-check scope.
- `.github/workflows/visual.yml`: install optional HTTP/test extras for CI regression.
- `.env.example`: non-secret runtime placeholders only; no `.env` edit or secret exposure.
- `README.md`: adapter, launch/setup boundary and testing state.
- `docs/http-integration.md`: implemented visual surface, no longer docs-only.
- `docs/architecture/repository-structure.md`: optional fourth package/dependency boundary.
- `docs/architecture/parallel-engineering-track-v1.md`: B1 implementation status only.
- `reports/PHASE2_TEXT_RETRIEVAL_EXECUTION_PLAN.md`: visual HTTP status, not text progress.

No Git metadata exists in this checkout; no commit/push/branch/init was performed. Review
covered the explicit file inventory, new sources, dependency pins and schema/manifest hashes.
Generated HTTP schemas are intentional source-controlled contract artifacts, not datasets.

## Limitations and stopping point

Internal adapter engineering is GREEN; production publication remains blocked on an actual
backend/gateway's authentication/authorization, canonical enrichment integration, rate limits,
deployment isolation/assets/resources, and operational/SLO checks. Loopback is not identity.
Annotation/runtime access separation is a process/deployment requirement, not implemented auth.
No container, watchdog, hot index reload, request telemetry or other speculative infrastructure.

Stop at visual-only HTTP V1. Human queries/judgments remain the separate Track A gate; no
text retrieval, FTS, BM25, voice, RAG, dense/fusion or business API work starts automatically.
