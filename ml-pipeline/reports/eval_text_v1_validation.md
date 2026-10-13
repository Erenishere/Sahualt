# EVAL-TEXT-V1 protocol gate validation

Protocol registration/validator gate: **GREEN**. EVAL-TEXT-V1 human dataset and benchmark:
**PENDING**, not GREEN or complete. No query set or relevance labels were invented.

## Verified source and policy

- Registered corpus: `PRODUCT-TEXT-V1`, 400 canonical Product documents.
- Corpus SHA-256: `5067202e69fbe0dfd61601e23cfe037a88fcc39a533c923dbdab270e0208e43f`.
- Protocol fingerprint: `sha256:d6412182594f8c10b6bc950120e4997390b8ab8f5130fda441f4cfaf476175e6`.
- Actual freeze stage: `PENDING_HUMAN_QUERIES_AND_LABELS`; counts remain null/PENDING.
- Minimum human workload: 40 English semantic queries, 20 queries/independent intents per
  dev/test split, complete two-judge coverage of 400 Products: 32,000 primary rows.
- Primary metric policy: nDCG@10; no metric execution or text-only quality threshold.
- FTS remains proposal Baseline A after ADR-ML-002; no BM25 substitution approved here.

## Executed checks

```powershell
python scripts/prepare_text_evaluation.py preregister
python scripts/prepare_text_evaluation.py preregister
python scripts/prepare_text_evaluation.py verify
python scripts/prepare_text_evaluation.py freeze-labels
python -m pytest tests/text/unit/test_text_evaluation.py -q
$env:RUN_DATABASE_TESTS='1'
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m mypy
```

The first three commands succeed with an identical registered protocol and corpus. The
fourth is an intentional negative check: it refuses missing `--judgments`, generates no labels
and does not create a qrels/dataset manifest. Only `readiness.json` exists in the real
evaluation artifact directory; human query/judgment/adjudication artifacts are absent.

| Check | Executed result |
| --- | --- |
| New synthetic protocol/annotation tests | 50 passed |
| Full repository suite, PostgreSQL enabled | 255 passed, 2 opt-in model tests skipped |
| Existing database regression coverage within full suite | 56 passed |
| Fixture ingestion, projection/corpus and Visual V1 regressions | Passed within full suite |
| Ruff lint | Passed |
| Ruff format | 94 files already formatted |
| mypy | Passed, 62 source files |

Synthetic fixtures test validation/determinism only, never corpus/evaluation evidence.
Database regressions use isolated temporary databases; this gate does not mutate canonical
business data or schema. No pretrained-model result is re-claimed by the skipped model tests.

## Artifacts and implementation

- `configs/eval_text_v1.yaml` and `configs/eval_text_v1.protocol.json`: frozen machine policy/lock.
- `docs/EVAL-TEXT-V1.md`, `docs/text-labeling-v1.md`: metric/label/split/timing contracts.
- `src/sahulat_text/evaluation/`: protocol, labeling, artifact integrity and CLI boundaries.
- `scripts/prepare_text_evaluation.py`: thin offline entry point.
- `tests/text/unit/test_text_evaluation.py`: synthetic regression fixtures.
- `artifacts/eval_text_v1/readiness.json`, `reports/eval_text_v1_readiness.md`: deterministic
  measured readiness, separately from this execution report.
- README, repository structure, corpus documentation and Phase 2/traceability plan updated
  only to distinguish protocol completion from pending labels/results.

No retriever, metric runner, queries, human labels, Search/Commerce schema, FTS, tsvector,
GIN/vector index, pgvector, embeddings, RRF, API, authentication or Visual V1 change.

## Remaining blockers and stop

Humans must supply representative in-scope queries, confirm intent groups/splits and scope,
then independently label/adjudicate the full matrix. Validators cannot establish human
authorship, relevance truth or held-out access compliance. Checksum freezing is not access
control. Until genuine data passes that workflow, EVAL-TEXT-V1 is not benchmark-ready.
ADR-ML-002 must separately freeze PostgreSQL lexical configuration before any Baseline A
implementation or evaluation. This task stops at protocol registration and validation.
