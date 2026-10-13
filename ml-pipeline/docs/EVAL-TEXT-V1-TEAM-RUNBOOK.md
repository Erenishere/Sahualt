# EVAL-TEXT-V1 team runbook

Operational guide for Adeel, Bisma, and Erum during **human query and label collection**.  
Does not change the frozen protocol. Does not include benchmark query text.

**Coordinator docs:** [checklist](EVAL-TEXT-V1-COORDINATOR-CHECKLIST.md) · [query workflow](TEXT-QUERY-V1-WORKFLOW.md) · [labeling contract](text-labeling-v1.md)

---

## Current gate (engineering)

| Item | Status |
| --- | --- |
| product-text-v1 corpus | FROZEN (400) |
| TEXT-QUERY-V1 tooling | FROZEN / GREEN |
| Coordinator templates + checklist | READY |
| Judging product CSV export | READY (`export_text_judging_products.py`) |
| 40 human queries | PENDING |
| Query freeze (EVAL-TEXT-V1-QUERY-FREEZE) | PENDING |
| 32,000 primary judgments | PENDING |
| Label freeze | PENDING |
| Text retrieval prototypes (A/B/D) | FROZEN — [ENGINEERING-TEXT-PROTOTYPE-V1](ENGINEERING-TEXT-PROTOTYPE-V1.md) |
| Official EVAL-TEXT-V1 retriever eval | BLOCKED (`HUMAN_LABEL_FREEZE_PENDING`) |

Check status anytime:

```powershell
python scripts/text_eval_coordinator_status.py
python scripts/engineering_text_prototype_status.py
```

---

## Roles

| Role | Who | Rules |
| --- | --- | --- |
| **Coordinator** | One named person | Sole `import-queries` / freeze / verify; keeps alias maps private |
| **Query authors** | Adeel, Bisma, Erum | Write assigned queries; may read frozen product **text** only |
| **Primary judges** | Rotate (see below) | Grade every query × **all 400** products; never the query author for that query |
| **Adjudicator** | Third human | Only where two primaries disagree on grade |

Authors and judges must **not** use retrieval demos, rankings, or scores while working on these queries.

---

## Stage A — Query collection (NOW)

### 1. Coordinator pre-assigns IDs

Copy [coordinator_query_assignments.template.csv](../configs/examples/eval_text_v1/coordinator_query_assignments.template.csv).

It fixes:

- 40 queries, 40 intent groups (one query per group)
- 20 dev + 20 test
- All five query classes in **each** split (four queries per class per split)
- Author slots: **Adeel 14**, **Bisma 13**, **Erum 13**

Authors replace `assigned_author_id` with their opaque alias if different (`adeel`, `bisma`, `erum` satisfy the schema).

### 2. Authors write queries

Each author fills **only their rows** with genuine English semantic shopping language.

Export to JSONL with **exactly eight fields** per [checklist §2](EVAL-TEXT-V1-COORDINATOR-CHECKLIST.md):

`query_id`, `query_text`, `language_tag`, `query_class`, `split`, `intent_group_id`, `author_id`, `authorship`

Do **not** copy product titles verbatim as a shortcut. Do **not** use an LLM to draft queries.

### 3. Coordinator imports and tracks

```powershell
python scripts/export_text_judging_products.py --output data/eval_text_v1/judging_products.csv
python scripts/prepare_text_evaluation.py import-queries --queries path/to/author-batch.jsonl
python scripts/prepare_text_evaluation.py query-status
python scripts/text_eval_coordinator_status.py
```

Repeat import as batches arrive until coverage passes.

### 4. Query freeze gate

```powershell
python scripts/prepare_text_evaluation.py validate-queries
python scripts/prepare_text_evaluation.py freeze-queries
python scripts/prepare_text_evaluation.py verify-queries
```

**Stop engineering** after this gate until Stage B completes. No FTS/dense/RRF/API work.

---

## Stage B — Judging (after query freeze only)

### Matrix

Every frozen query uses the **same 400 products** from `judging_products.csv`:

```text
40 queries × 400 products × 2 primary judges = 32,000 judgment rows
```

Optional extra rows: adjudications for disagreements only.

### Suggested judge rotation

Query author cannot judge their own query. Example assignment pattern:

| Query author | Primary judge A | Primary judge B |
| --- | --- | --- |
| Adeel | Bisma | Erum |
| Bisma | Adeel | Erum |
| Erum | Adeel | Bisma |

Coordinator records fixed judge pairs per `query_id` in a private sheet (use [judgment progress template](../configs/examples/eval_text_v1/judgment_progress_tracker.template.csv)).

### Judgment file

`data/eval_text_v1/human_judgments.jsonl` — six fields per row; see [text-labeling-v1](text-labeling-v1.md).

Use `product_id` from the judging CSV (canonical UUID). Grades 0/1/2 with protocol rationales.

### Label freeze

```powershell
python scripts/prepare_text_evaluation.py freeze-labels `
  --judgments data/eval_text_v1/human_judgments.jsonl `
  --adjudications data/eval_text_v1/human_adjudications.jsonl
python scripts/prepare_text_evaluation.py verify
```

When readiness reports dataset ready, engineering may start **ADR-ML-002** and PostgreSQL FTS Baseline A.

---

## Parallel engineering (prototype only)

FTS Baseline A may be developed on a **feature branch** using **synthetic toy catalogues**
only. See [ADR-ML-002 draft](ADR-ML-002-postgresql-fts-lexical-baseline-a.md) and
`src/sahulat_text/retrievers/lexical/`. Do **not** run official EVAL-TEXT-V1 benchmarks or
index the frozen 400-product corpus for tuning while humans collect queries/labels.

```powershell
python scripts/apply_search_lexical_migration.py
python scripts/build_lexical_index_prototype.py --toy
python scripts/smoke_lexical_retriever_prototype.py --query "red shirt" --corpus-sha256 bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
```

See [LEXICAL-RETRIEVER-PROTOTYPE-V1.md](LEXICAL-RETRIEVER-PROTOTYPE-V1.md).

Dense prototype (requires pgvector):

```powershell
python scripts/apply_search_dense_migration.py
python scripts/build_dense_index_prototype.py --toy
python scripts/smoke_dense_retriever_prototype.py --query "red shirt" --top-k 3
```

See [DENSE-RETRIEVER-PROTOTYPE-V1.md](DENSE-RETRIEVER-PROTOTYPE-V1.md).

Hybrid RRF (lexical + dense indexes required):

```powershell
python scripts/smoke_hybrid_retriever_prototype.py --query "red shirt" --top-k 3
```

See [HYBRID-RETRIEVER-PROTOTYPE-V1.md](HYBRID-RETRIEVER-PROTOTYPE-V1.md).

## What not to do during Stages A–B

- Official EVAL-TEXT-V1 metrics or tuning on the frozen benchmark  
- Dense embeddings, pgvector, RRF (after isolated FTS prototype)  
- `/search/text` or voice→search  
- Tune or prototype retrievers on draft queries  
- Reopen Visual V1, voice eval gates, or the frozen corpus  

---

## After label freeze (engineering resume order)

1. ADR-ML-002 → lexical Baseline A + eval on frozen test split  
2. Dense Baseline B + eval  
3. Hybrid RRF Baseline D + eval  
4. ADR-ML-005 (or equivalent) → lock Text Retrieval V1  
5. Text HTTP adapter → then voice→text  

Voice parallel track (does not unblock text): Pashto provenance, Sindhi holdout.
