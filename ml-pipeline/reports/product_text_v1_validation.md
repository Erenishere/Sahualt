# product-text-v1 gate verification

Status: **GREEN**  
Date: 2026-09-12  
ADR-ML-004: **ACCEPTED**

## Executed verification

| Check | Result |
| --- | --- |
| Product-document unit tests | 38 passed |
| PostgreSQL Product projection/document tests | 18 passed, included in database/full suites |
| Database regression suite | 56 passed |
| Full repository suite with `RUN_DATABASE_TESTS=1` | 191 passed, 2 opt-in pretrained model tests skipped |
| CI-style fast selection | 137 passed, 56 deselected (54 database-marked + 2 model tests) |
| Ruff lint | Passed |
| Ruff formatting | Passed; 85 Python files formatted |
| mypy | Passed; 57 source files |
| Live schema/integrity review | GREEN on PostgreSQL 18.6 / `sahulat_ai_dev` |
| Gate 1 audit regeneration | Identical canonical evidence; no frozen evidence modified |
| Verified fixture ingestion lineage/parity | GREEN; original source and semantic checksum preserved |
| Independent CLI rerun | JSONL and manifest byte-identical |
| Persisted manifest/artifact/document checksums | GREEN |
| Markdown reproduced from reloaded canonical JSON evidence | GREEN, with round-trip regression test |
| Generated-artifact secrets/Windows path checks | No configured password or machine-specific Windows path found |

Synthetic unit/database fixtures are test data only, never benchmark evidence. Integration tests
create uniquely named empty temporary databases, apply Migration 001 and remove only those
test-owned databases afterward. The live catalog is read-only throughout this document gate.
The Windows Unicode insert regression uses UTF-8 stdin; SQL passed through Windows process
arguments is not a Unicode ingestion interface. The canonical loader uses ASCII SQL and
explicit UTF-8 results, and existing canonical ingestion already uses UTF-8 stdin.

Commands executed using the existing virtual environment:

```powershell
$env:RUN_DATABASE_TESTS='1'
python -m pytest tests/text/unit/test_product_documents.py -q
python -m pytest tests/database -q
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m mypy
python scripts/build_product_text_v1.py --verify-khaadi-lineage
```

## Measured canonical build

| Measure | Count |
| --- | ---: |
| Canonical Products read / eligible / documents | 400 / 400 / 400 |
| Excluded Products | 0 |
| Products with / without Color | 400 / 0 |
| Multi-color Products | 0 |
| JSONL bytes | 153596 |

Artifact SHA-256:
`5067202e69fbe0dfd61601e23cfe037a88fcc39a533c923dbdab270e0208e43f`

Fixture semantic checksum:
`0a686d197ec1bdac3ea49bfe0a8ee9487db95d6c6967d72c909d5cc490eab900`

Per-document checksums, field parity, eligibility/exclusions, build observations and fixture
lineage are recorded in `artifacts/product_documents/product-text-v1-build.json`; the Markdown
build report is generated from that evidence. Canonical JSONL and manifest are deterministic;
the separately recorded observational durations are intentionally run-specific.

## Files created

- `src/sahulat_text/normalization.py`
- `src/sahulat_text/documents/projection.py`
- `src/sahulat_text/documents/builder.py`
- `src/sahulat_text/documents/serialization.py`
- `src/sahulat_text/documents/repository.py`
- `src/sahulat_text/documents/artifacts.py`
- `src/sahulat_text/documents/cli.py`
- `scripts/build_product_text_v1.py`
- `tests/text/unit/test_product_documents.py`
- `tests/database/test_product_documents.py`
- `docs/ADR-ML-004-product-text-document-construction.md`
- `reports/product_text_v1_build.md`
- `reports/product_text_v1_validation.md`
- `artifacts/product_documents/product-text-v1.jsonl`
- `artifacts/product_documents/product-text-v1.manifest.json`
- `artifacts/product_documents/product-text-v1-build.json`

## Files modified

- `src/sahulat_text/documents/__init__.py`: public pure builder/projection boundary.
- `src/sahulat_text/metadata_audit.py`: reuse the identical shared normalization implementation.
- `src/sahulat_text/ingestion/contracts.py`: preserve the public normalization alias and semantics.
- `src/sahulat_database/migrations.py`: redact passwords in configuration repr and explicitly
  exchange/decode UTF-8 PostgreSQL results without silent decoding replacement.
- `pyproject.toml`: add the document-build console entry point; no dependency changes.
- `README.md`: current database/document status, build command and validation instructions.
- `docs/architecture/repository-structure.md`: canonical projection and derived artifact boundary.
- `reports/PHASE2_TEXT_RETRIEVAL_EXECUTION_PLAN.md`: document-gate completion and traceability only.

Source datasets, ADR-DATA-001, DB-CONTRACT-V1, migrations, fixture mappings and Visual V1
semantics were not changed. Generated artifacts retain the repository's ignored-artifact policy.
This workspace has no Git metadata, so a Git diff/commit was not available or performed;
relevant changed files and generated evidence were inspected directly.

## Architectural decisions and remaining gates

- PostgreSQL remains business truth; JSONL is deterministic derived evidence.
- Builder inputs are immutable and fixture-independent; no commercial or image fields leak in.
- Non-archived drafts are eligible for document construction, not active commercial search.
- Colors use the frozen NFKC / exact deduplication / Unicode-sorted comma-space rendering policy.
- Python 3.12 / Unicode 15.0.0 is required for document builds to prevent normalization-table drift.
- Dedicated non-superuser runtime roles remain a platform task, not redesigned here.

No Search schema/tables, FTS/tsvector/GIN search index, pgvector, embeddings, retriever,
RRF, relevance labels, Commerce, API or indexing consumer was created. EVAL-TEXT-V1 remains
blocked on its frozen protocol/query set and human judgments. ADR-ML-002 needs an accepted
PostgreSQL lexical configuration. Stop at this GREEN gate.
