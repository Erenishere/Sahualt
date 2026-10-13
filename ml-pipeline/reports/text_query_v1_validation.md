# Human Query Authoring / Validation / Freeze gate

Tooling status: **GREEN / VERIFIED**. **HUMAN QUERY DATA: PENDING**. Query freeze: **PENDING**.
Genuine human query count: **0**. No query artifact checksum exists; no human dataset was
frozen. This report does not mark the human-data gate GREEN based on synthetic tests.

## Authoritative audit before implementation

Reviewed the existing EVAL-TEXT-V1 protocol, labeling contract, YAML/semantic lock, registered
corpus and source manifest metadata, accepted ADR-DATA-001 / ADR-ML-004, corpus documentation,
evaluation validation/readiness evidence, package/CLI layout and tests. The implementation
extends existing validators/freezing rather than creating a parallel dataset system.

- Protocol: `EVAL-TEXT-V1`, frozen and preregistered.
- Protocol fingerprint: `sha256:d6412182594f8c10b6bc950120e4997390b8ab8f5130fda441f4cfaf476175e6`.
- Contract: `docs/EVAL-TEXT-V1.md`, `docs/text-labeling-v1.md`.
- Corpus: `PRODUCT-TEXT-V1`, exactly 400 canonical documents.
- Corpus SHA-256: `5067202e69fbe0dfd61601e23cfe037a88fcc39a533c923dbdab270e0208e43f`.
- Corpus/protocol verification: **GREEN**, executed against the registered immutable snapshot.
- Runtime: Python 3.12 / Unicode 15.0.0, using existing dependencies only.
- No authoritative ADR, contract, corpus, protocol config or lock was modified.

## Implementation and validation rules

The established `prepare_text_evaluation.py` CLI now supports `import-queries`,
`validate-queries`, `freeze-queries`, `verify-queries` and `query-status`. It can also be invoked
through `python -m sahulat_text.evaluation.cli`. Workflow:
[TEXT-QUERY-V1-WORKFLOW.md](../docs/TEXT-QUERY-V1-WORKFLOW.md).

Each source query still has exactly eight required fields: `query_id`, `query_text`,
`language_tag`, `query_class`, `split`, `intent_group_id`, `author_id`, `authorship`.
No timestamps, version fields or research dimensions were appended to query records.
IDs, classes, groups and splits remain coordinator-owned, not generated/inferred by software.
Technical schema identity (`text-query-input-v1`) lives in sidecar metadata only.

Strict validation covers explicit string metadata, IDs/aliases, declared English language,
human authorship, nonblank text, 512-code-point limit, no control/unpaired-surrogate characters,
exact schema, duplicate IDs/text, normalized duplicates and dev/test intent separation.
Normalization/casefold is for duplicate comparison only; human text is preserved verbatim.
Malformed JSON/UTF-8, duplicate JSON keys and nonfinite numbers fail closed. Errors identify
row positions, prohibited/missing fields or concrete coverage deficits without suggesting
replacement queries.

Incremental collection permits valid partial submissions but **not** a partial freeze or
GREEN human-data gate. Complete validation/freeze requires >=40 queries, >=20 queries and
20 independent intents per split, and all five configured classes in each split. Missing
metadata/strata cannot be inferred to make acceptance pass. Actual measured coverage:

| Requirement | Current measurement | Status |
| --- | --- | --- |
| Genuine human queries | 0 / minimum 40 | PENDING / not satisfied |
| Dev queries / independent intents | 0 / 0; minimum 20 / 20 | Not satisfied |
| Test queries / independent intents | 0 / 0; minimum 20 / 20 | Not satisfied |
| Every configured class in each split | All counts 0; minimum 1 each | Not satisfied |
| Query freeze/checksum | No query JSONL or manifest | PENDING |

## Determinism, integrity and blinding

Unchanged import is an idempotent no-op; conflicting reused IDs are errors. Source submissions
remain human-authored. Collection receipts bind source-byte hashes, canonical record hashes,
collection checksum and corpus/protocol/schema identities. An exclusive local import lock
serializes import writers. Interrupted/orphan receipt pairs fail closed. A coordinator must
serialize review/import/freeze; this is not a concurrent authoring application or a multi-file
transaction. Explicit human-reviewed corrections preserve prior evidence; no silent overwrites.

Freeze uses the existing artifact filenames/manifest version with technical schema/runtime,
coverage and per-record checksum metadata. Query rows are query-ID sorted, compact sorted-key
JSON, strict UTF-8, no nonfinite numbers and one LF per record. SHA-256 binds exact bytes.
Unchanged freezes preserve identical bytes and modification times. Verification independently
revalidates record rules and recomputes every checksum, count/coverage, version and canonical
serialization/order; rehashed but inconsistent metadata or ordering still fails.

Query-only actions never read judging artifacts and reject judging arguments. Exact field
allowlists reject product/retrieval/results/score/prediction/label metadata, including nested
extras. Tests guard no retriever/model imports and no calls to judging/readiness loaders.
Coordinator review is still necessary: software cannot establish genuine human authorship,
actual English semantic scope, independent intents or whether a person saw outside results.
No human-data GREEN claim is derived from declarations or synthetic fixtures alone.

## Executed verification

```powershell
python scripts/prepare_text_evaluation.py verify
python scripts/prepare_text_evaluation.py query-status --status-output artifacts/eval_text_v1/text-query-v1-status.json
python scripts/prepare_text_evaluation.py validate-queries
python scripts/prepare_text_evaluation.py freeze-queries
python scripts/prepare_text_evaluation.py verify-queries
python -m pytest tests/text/unit/test_human_queries.py -q
$env:RUN_DATABASE_TESTS='1'
python -m pytest -q
python -m pytest tests/database -q
python -m ruff check .
python -m ruff format --check .
python -m mypy
```

General protocol/corpus verification succeeds. Status measures zero queries and PENDING
data/freeze without creating a human-input file. The three query validation/freeze/verify
commands are intentional negative checks: absent human input/frozen files are refused.
Only neutral status evidence was produced, not an empty frozen query artifact.

| Test/check | Actual result |
| --- | --- |
| New query-gate tests, synthetic test fixtures only | 56 passed |
| Existing protocol/annotation tests | 50 passed, maintained |
| Full repository suite, PostgreSQL enabled | 311 passed, 2 opt-in model tests skipped |
| Dedicated database regression suite | 56 passed |
| Fixture ingestion / corpus / document projection / Visual V1 regressions | Passed within full suite |
| Ruff | Passed |
| Formatting | Passed, 96 files already formatted |
| mypy | Passed, 63 source files |

Database tests use isolated temporary databases after Migration 001; canonical business data
and schema are unchanged. Synthetic test queries/grades from existing regression fixtures are
not human benchmark evidence; no new judging dataset, relevance rows or assignments were made.

## Complete intentional file inventory

| Path | Change |
| --- | --- |
| `src/sahulat_text/evaluation/queries.py` | Added incremental collection, provenance receipt, lock and query-only status |
| `src/sahulat_text/evaluation/labeling.py` | Extended existing validator with explicit partial-collection mode, coverage diagnostics and strict Unicode/JSON parsing |
| `src/sahulat_text/evaluation/artifacts.py` | Extended query manifest and canonical byte/metadata/per-record verification; no judging semantics changed |
| `src/sahulat_text/evaluation/protocol.py` | Enforced existing protocol lock's exact canonical bytes, not merely parsed-object equality |
| `src/sahulat_text/evaluation/cli.py` | Extended existing CLI with import/validation/query-only verification/status; fail-closed argument checks |
| `tests/text/unit/test_human_queries.py` | Added 56 focused synthetic tests, never benchmark evidence |
| `docs/TEXT-QUERY-V1-WORKFLOW.md` | Added coordinator workflow, deterministic serialization and blinding/limitations |
| `README.md` | Linked the human-query workflow and status command |
| `docs/architecture/repository-structure.md` | Documented query-only dependency/collection boundary |
| `artifacts/eval_text_v1/text-query-v1-status.json` | Added neutral deterministic evidence: 0 human queries, freeze PENDING |
| `reports/text_query_v1_validation.md` | Added this execution/validation report |

Existing `artifacts/eval_text_v1/readiness.json` and `reports/eval_text_v1_readiness.md` were
regenerated byte-identically by the existing general verification command; no semantic change.
Normal ignored test/tool caches are excluded from this intentional inventory. The workspace
has no Git metadata; no repository initialization, commit, branch or push was performed.

## Blockers, forbidden-work confirmation and stop

The canonical human input `data/eval_text_v1/human_queries.jsonl` is absent. Humans must
actually supply the required query set and coordinator review before query freeze can be
GREEN. Until then query artifact SHA-256 is intentionally absent. No labels or adjudications
are needed/executed in this gate, and no 32,000-row assignment artifact is generated.

No queries fabricated; no relevance labels fabricated; no PostgreSQL FTS, tsvector/tsquery,
BM25, ranking functions, embeddings/vectors, retriever or Search infrastructure created.
No ADR-ML-002 decision, models, database writes/migrations, APIs, retrieval results, metrics,
Commerce or Visual V1 changes. BM25 remains unapproved; PostgreSQL FTS remains the frozen
future lexical baseline. **STOP: tooling GREEN, human query data/freeze PENDING.**
