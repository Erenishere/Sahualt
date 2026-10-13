# ENGINEERING-TEXT-PROTOTYPE-V1 (frozen)

**Date frozen:** 2026-09-26  
**Scope:** Implementation proof only — **not** official EVAL-TEXT-V1 benchmark evidence.

## Gate status

```text
ENGINEERING-TEXT-PROTOTYPE-V1

Lexical prototype (A):     PASS — PostgresLexicalRetriever + migration 002
Dense prototype (B):       PASS — PostgresDenseRetriever + ToyTextEncoder + migration 003
Hybrid prototype (D):      PASS — HybridRRFRetriever + reciprocal_rank_fusion
Synthetic / unit tests:    PASS — see scripts/engineering_text_prototype_status.py --verify-unit
Toy DB smoke (operator):   RUN LOCALLY — requires PostgreSQL + pgvector + psql on PATH
Official EVAL-TEXT-V1:     BLOCKED
Reason:                    HUMAN_LABEL_FREEZE_PENDING
```

Print current banner anytime:

```powershell
python scripts/engineering_text_prototype_status.py
```

## What this freeze means

- **Do not** extend retrieval code, prototype YAML configs, or migrations until human labels freeze
  and the **official evaluation harness** is explicitly opened.
- **Do not** treat toy cosine rankings, `rrf_k=60`, or `ToyTextEncoder` as production decisions.
- ADR-ML-002 and ADR-ML-003 remain **DRAFT / prototype** — not production encoder or Baseline
  benchmark claims.

## Frozen prototype configs (do not edit)

| File | Role |
| --- | --- |
| `configs/lexical_retriever_prototype_v1.yaml` | Baseline A prototype |
| `configs/dense_retriever_prototype_v1.yaml` | Baseline B toy encoder |
| `configs/hybrid_retriever_prototype_v1.yaml` | Baseline D RRF parameters |

## Operator toy smoke (final acceptance on your machine)

After migrations and `--toy` index builds (corpus SHA-256 = 64× `b`):

```powershell
python scripts/build_lexical_index_prototype.py --toy
python scripts/build_dense_index_prototype.py --toy
python scripts/smoke_lexical_retriever_prototype.py --query "red shirt" --top-k 3 --corpus-sha256 ("b"*64)
python scripts/smoke_dense_retriever_prototype.py --query "red shirt" --top-k 3
python scripts/smoke_hybrid_retriever_prototype.py --query "red shirt" --top-k 3
```

Corpus mismatch guard (unit-tested; no DB):

```powershell
python -m pytest tests/text/unit/test_hybrid_retriever.py::test_hybrid_rejects_corpus_mismatch -q
```

## Human track (active priority)

```text
0/40 queries
   → 40 genuine human queries
   → validate-queries → freeze-queries → verify-queries
   → 32,000 judgments → adjudications → freeze-labels → verify
   → ENGINEERING UNLOCK (official evaluator)
```

Coordinator dashboard:

```powershell
python scripts/text_eval_coordinator_status.py
```

Runbook: [EVAL-TEXT-V1-TEAM-RUNBOOK.md](EVAL-TEXT-V1-TEAM-RUNBOOK.md).

## After label freeze — first engineering task

Build the **official evaluation harness** on frozen corpus + queries + qrels, then run:

```text
Baseline A (lexical) → Baseline B (dense) → Baseline D (hybrid RRF)
→ DEV analysis → config freeze → TEST evaluation → comparison report
```

## References

| Artifact | Path |
| --- | --- |
| ADR lexical (draft) | [ADR-ML-002](ADR-ML-002-postgresql-fts-lexical-baseline-a.md) |
| ADR dense (draft) | [ADR-ML-003](ADR-ML-003-dense-text-retrieval-prototype.md) |
| Lexical how-to | [LEXICAL-RETRIEVER-PROTOTYPE-V1.md](LEXICAL-RETRIEVER-PROTOTYPE-V1.md) |
| Dense how-to | [DENSE-RETRIEVER-PROTOTYPE-V1.md](DENSE-RETRIEVER-PROTOTYPE-V1.md) |
| Hybrid how-to | [HYBRID-RETRIEVER-PROTOTYPE-V1.md](HYBRID-RETRIEVER-PROTOTYPE-V1.md) |
| Freeze evidence | [reports/engineering_text_prototype_v1_freeze.md](../reports/engineering_text_prototype_v1_freeze.md) |
| Gate registry | [configs/gates/engineering_text_prototype_v1.json](../configs/gates/engineering_text_prototype_v1.json) |
