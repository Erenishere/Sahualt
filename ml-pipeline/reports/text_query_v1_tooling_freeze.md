# TEXT-QUERY-V1 tooling freeze and parallel engineering boundary

| Gate | Verified status |
| --- | --- |
| TEXT-QUERY-V1 tooling | **FROZEN / GREEN** |
| Genuine human query dataset | **PENDING: 0 queries** |
| Query dataset freeze | **NOT POSSIBLE** |
| EVAL-TEXT-V1 protocol | **FROZEN**, existing corpus/protocol verification passes |
| TEXT-EVAL-DATASET-V1 | **Not frozen, not GREEN** |
| Text retrieval / PostgreSQL FTS / dense / RRF | **BLOCKED** |

## Software freeze, not an empty benchmark

Registry: `configs/gates/text_query_tooling_v1.json`.
Software snapshot SHA-256: `sha256:d435e6a1b39d7eed49f4bd903b8a4d6dcd5f3e72bad8bcd562977e8a6849c568`.
Preserved bundle:
`artifacts/tooling/text-query-v1/d435e6a1b39d7eed49f4bd903b8a4d6dcd5f3e72bad8bcd562977e8a6849c568/`.

The bundle contains 19 selected source/contract/config/test/prior-validation files plus its
canonical manifest. The registry lists each path and exact-byte checksum. It binds the
unchanged EVAL-TEXT-V1 protocol and PRODUCT-TEXT-V1 corpus (400 documents, SHA-256
`5067202e69fbe0dfd61601e23cfe037a88fcc39a533c923dbdab270e0208e43f`).
Scope is explicitly software/validation evidence, not human queries, judgments or a standalone
deployable package. Freeze-management code/tests and ongoing Track B docs live separately
in source control; their execution evidence is recorded below. Shared repository/deployment
dependencies outside the listed inventory are not claimed to be fully bundled.

No query artifact checksum, empty query JSONL, qrels, assignments or fabricated human rows
are produced. `data/eval_text_v1/human_queries.jsonl` is still absent. The software registry
records PENDING/zero human data **at tooling freeze**, not an eternal live-data assertion.
Use the existing query status command to inspect future human collection independently.

## Verify and version

```powershell
python scripts/freeze_text_query_tooling.py
python scripts/freeze_text_query_tooling.py --verify-only
python scripts/freeze_text_query_tooling.py --verify-only --check-working-tree
python scripts/prepare_text_evaluation.py query-status
```

First registration validates protocol/corpus and absent human data, preserves exact source
bytes and emits a deterministic, self-checksummed registry/manifest. Repeated unchanged
registration is a no-op, never an overwrite. Paths are portable repository-relative references;
there are no secrets, timestamps or machine-specific absolute paths in canonical metadata.
Exact snapshot bytes retain their original line endings: distribute/preserve them rather
than treating a new checkout's automatic line-ending conversion as identical file bytes.

Default verification reads saved software and verifies every file hash/manifest, even if later
Track B work changes the repository. `--check-working-tree` additionally detects deviation in
the listed source files. Refreezing changed software at V1 is refused; preserve this registry
and bundle, then explicitly version future tooling changes. Canonical artifact corruption,
metadata drift and path escapes fail; no automatic repair. Per-file writes are atomic, not
a multi-file transaction or access-control mechanism. Preserve the ignored artifact bundle
separately with its source-controlled registry. No Git initialization/commit/push was made.

## Executed validation

- Freeze registered twice and verified with current-working-tree checks: **PASS**; identical SHA-256.
- New software-freeze tests: **15 passed**, synthetic snapshots only, not benchmark evidence.
- Full repository suite with PostgreSQL enabled: **326 passed, 2 opt-in model tests skipped**.
- Existing database, fixture ingestion, query/protocol/corpus and Visual V1 regression coverage:
  **passed within the full suite**. Database tests use isolated temporary databases.
- Ruff: **PASS**. Formatting: **PASS**, 99 files already formatted. mypy: **PASS**, 64 source files.
- Real human query/frozen-artifact presence check: **0 / absent**, no query dataset frozen.

## Track B work completed here

[Parallel engineering architecture](../docs/architecture/parallel-engineering-track-v1.md)
defines the proposed .NET/business-data versus Python/research/runtime boundary, visual-only
HTTP lifecycle/identity/security considerations, annotation blinding, deployment exclusions,
voice adapter dependencies and authorized vendor-assistant source requirements.

This is a dependency-labelled **architecture plan**, not FastAPI/voice/RAG implementation.
The existing integration note was corrected to acknowledge the canonical PostgreSQL/Migration
001 foundation; it does not introduce pgvector. Visual MAX aggregation, identities and
EVAL-VISUAL-V1 remain unchanged. Current source-derived draft listings are not activated.

Track A still requires genuine authoring/review, >=40 English queries with frozen split/intent/
class coverage, then exhaustive independent judging/adjudication and genuine evaluation
dataset freeze. ~50 raw submissions from multiple humans do not guarantee acceptance, and
query-authoring time does not imply completion of 32,000 primary-judge rows. PostgreSQL FTS
remains the lexical baseline; no BM25 approval or ADR-ML-002 decision was created.

## Intentional file inventory

- Added `src/sahulat_text/evaluation/tooling.py`: software-only registry/snapshot verification.
- Added `scripts/freeze_text_query_tooling.py`: freeze/verify entry point.
- Added `tests/text/unit/test_tooling_freeze.py`: 15 focused tests.
- Added `configs/gates/text_query_tooling_v1.json`: immutable software registry.
- Added the checksummed software bundle under `artifacts/tooling/text-query-v1/` (19 files + manifest).
- Added `docs/architecture/parallel-engineering-track-v1.md`: proposed Track B/dependency plan.
- Added `reports/text_query_v1_tooling_freeze.md`: this execution report.
- Updated `README.md`, `docs/architecture/repository-structure.md`, `docs/http-integration.md`:
  distinguish tooling freeze from human-data readiness and correct stale integration context.

No accepted ADR, DB contract, migration, ingestion semantics, corpus/protocol/query tooling
source or Visual V1 core was changed by Track B. No text retriever, FTS, BM25, embeddings,
vectors, Search/Commerce infrastructure, relevance labels, API runtime, ASR/RAG model or
deployment was created. **Next bounded candidate: review/authorize the visual-only runtime
contract; text retrieval stays blocked while human data is PENDING.**
