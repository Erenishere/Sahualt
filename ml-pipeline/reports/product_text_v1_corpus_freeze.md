# PRODUCT-TEXT-V1 corpus registration

Status: **FROZEN / VERIFIED**. This is corpus registration only; EVAL-TEXT-V1 is not complete.

| Identity | Verified value |
| --- | --- |
| Corpus ID | `PRODUCT-TEXT-V1` |
| Records | 400 |
| JSONL bytes | 153596 |
| Corpus SHA-256 | `5067202e69fbe0dfd61601e23cfe037a88fcc39a533c923dbdab270e0208e43f` |
| Manifest bytes | 46615 |
| Manifest SHA-256 | `0b6506f645fc773a3e7405a6075fed8e71f11815d4b22eb3c5d9da761ec35e50` |
| Registry | `configs/corpora/product_text_v1.json` |
| Runtime | Python 3.12 / Unicode 15.0.0 |

The preserved snapshot is content-addressed under `artifacts/corpora/product-text-v1/`.
Source/snapshot bytes, manifest integrity, every document checksum and exact canonical
serialization were verified. Repeated registration preserved both bytes and modification times.
Tests confirm a changed working build does not change the frozen snapshot; drift/corruption,
false provenance, incorrect counts and escaping/nonportable paths are rejected.

## Executed checks

- Frozen-corpus unit tests: 14 passed, using synthetic fixtures only.
- Combined document/corpus unit tests: 52 passed.
- Full repository suite with `RUN_DATABASE_TESTS=1`: 205 passed, 2 opt-in model tests skipped.
- Ruff lint and formatting: passed (88 Python files).
- mypy: passed (58 source files).
- Registration, unchanged rerun and independent `--verify-only`: verified.

```powershell
python scripts/freeze_product_text_corpus.py --verify-only
```

Files added: registry, `src/sahulat_text/documents/corpus.py`,
`scripts/freeze_product_text_corpus.py`, `tests/text/unit/test_frozen_corpus.py`,
`docs/PRODUCT-TEXT-V1-CORPUS.md`, this report and the generated frozen JSONL/manifest snapshot.
README and the Phase 2 execution plan now reference the registered corpus. The existing
working documents, accepted ADRs, database contract, ingestion and Visual V1 are unchanged.
The registry is Git-trackable; this workspace still has no Git metadata. Generated snapshot
bytes follow the existing ignored-artifact policy and must be preserved separately.

No database writes, retrieval/search infrastructure, relevance labels or benchmark claims
were added. Next: EVAL-TEXT-V1 protocol/query set and human judgments, independently versioned
and bound to this corpus ID/hash. Keep nDCG@10 in the proposal-aligned metric set. PostgreSQL
FTS remains proposal-faithful Baseline A; BM25 requires an explicitly approved interim ADR.
