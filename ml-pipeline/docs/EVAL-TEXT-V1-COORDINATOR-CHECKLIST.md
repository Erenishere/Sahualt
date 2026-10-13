# EVAL-TEXT-V1 coordinator checklist

Status: operational guide for **human data collection only**.  
Authority: [EVAL-TEXT-V1](EVAL-TEXT-V1.md), [text-labeling-v1](text-labeling-v1.md), [TEXT-QUERY-V1-WORKFLOW](TEXT-QUERY-V1-WORKFLOW.md), `configs/eval_text_v1.yaml`.  
Corpus: **PRODUCT-TEXT-V1**, 400 products, SHA-256 `5067202e69fbe0dfd61601e23cfe037a88fcc39a533c923dbdab270e0208e43f`.

This document does **not** amend the frozen protocol. It does **not** contain benchmark queries suitable for submission.

**Team runbook (Adeel / Bisma / Erum):** [EVAL-TEXT-V1-TEAM-RUNBOOK.md](EVAL-TEXT-V1-TEAM-RUNBOOK.md)

**Gate dashboard:**

```powershell
python scripts/text_eval_coordinator_status.py
```

---

## 0. Before anyone writes a query

| Check | Action |
| --- | --- |
| Roles | Name one **coordinator** (sole importer/freezer), query **authors**, and (later) **judges** and **adjudicators**. |
| Blinding | Authors/judges must not see retrieval rankings, scores, or retriever demos on real query text. |
| Corpus access | Authors may read frozen semantic documents (`artifacts/corpora/product-text-v1/.../product-text-v1.jsonl` or build output) to craft **supported** intents—not to copy product titles as automatic queries. |
| Judging export | Judges use read-only CSV from frozen corpus (no retrieval fields): `python scripts/export_text_judging_products.py --output data/eval_text_v1/judging_products.csv` |
| Tooling | Python **3.12**, editable install, protocol verified: `python scripts/prepare_text_evaluation.py verify` (protocol lock only; human data may still be absent). |
| Locked tracks | Do not change Visual V1, voice eval gates, or `product-text-v1` corpus while collecting queries. |

---

## 1. Query requirements (minimum bar for freeze)

From `configs/eval_text_v1.yaml`:

| Requirement | Value |
| --- | --- |
| Total queries | ≥ **40** |
| Per split (`dev`, `test`) | ≥ **20** queries each |
| Intent groups per split | ≥ **20** independent groups each |
| Intent groups across splits | **Disjoint** (same `TXT-I-####` cannot appear in both splits) |
| Classes (each split needs ≥ 1 query in **each**) | `title_terms`, `attribute_focused`, `paraphrase`, `contrastive`, `sparse_description` |
| Language | `en` only |
| Authorship | `human` only |
| Query length | ≤ **512** Unicode code points |
| Scope | Semantic text only—no structured filters (price, size SKU filters, etc.) |

**Minimum cardinality pattern (40 queries, 40 intent groups):**  
Assign **one query per intent group** in dev (20 groups → 20 queries) and one per group in test (20 groups → 20 queries). Ensure each split hits all five classes at least once (e.g. distribute classes across the 20 rows).

Paraphrases of the **same** shopping intent share one `intent_group_id` and the **same** split; they count as one group, not two.

---

## 2. Query JSONL schema (exactly eight keys)

Each line is one JSON object. **No extra keys.** Field rules match `src/sahulat_text/evaluation/labeling.py`.

| Field | Rule |
| --- | --- |
| `query_id` | `TXT-Q-` + four digits, e.g. `TXT-Q-0001`, unique |
| `query_text` | Human text; non-blank; no ASCII/other control characters |
| `language_tag` | `en` |
| `query_class` | One of the five classes above |
| `split` | `dev` or `test` |
| `intent_group_id` | `TXT-I-` + four digits; stable per intent; one split only |
| `author_id` | Opaque alias `[a-z][a-z0-9_-]{1,63}`—not a real name or email |
| `authorship` | literal `human` |

Illustration only ( **do not import** — placeholder text):  
[configs/examples/eval_text_v1/SCHEMA-ILLUSTRATION-ONLY.query.jsonl](../configs/examples/eval_text_v1/SCHEMA-ILLUSTRATION-ONLY.query.jsonl)

---

## 3. Coverage tracker (spreadsheet)

Copy and fill locally (not validated by CI):

`configs/examples/eval_text_v1/query_coverage_tracker.template.csv`

Track until every cell meets minimums, then transcribe into JSONL for import.

Suggested columns: `query_id`, `split`, `query_class`, `intent_group_id`, `author_id`, `imported`, `notes`.

---

## 4. Query collection commands

Default collection path: `data/eval_text_v1/human_queries.jsonl`.

```powershell
# Incremental import from a human submission file
python scripts/prepare_text_evaluation.py import-queries --queries path/to/submission.jsonl

# Coverage inspection (works while PENDING)
python scripts/prepare_text_evaluation.py query-status
python scripts/prepare_text_evaluation.py query-status --status-output artifacts/eval_text_v1/text-query-v1-status.json

# Full gate (must pass before freeze)
python scripts/prepare_text_evaluation.py validate-queries

# Freeze canonical query artifact
python scripts/prepare_text_evaluation.py freeze-queries
python scripts/prepare_text_evaluation.py verify-queries
```

**Coordinator rules**

- Serialize import / validate / freeze (one writer; `.import.lock` on collection).
- Partial collection is fine until `validate-queries` passes.
- After query freeze starts under `artifacts/eval_text_v1/queries.jsonl`, do not edit the collection in place—version the dataset instead.
- Rejected submissions: keep reasons **outside** frozen artifacts.

### Phase 1A exit: query freeze

- [ ] `validate-queries` succeeds  
- [ ] `freeze-queries` + `verify-queries` succeed  
- [ ] `artifacts/eval_text_v1/queries.jsonl` + manifest checksums verified  
- [ ] No retriever or FTS code merged yet  

---

## 5. Judgment requirements (after query freeze)

| Requirement | Value |
| --- | --- |
| Primary rows | **40 × 400 × 2 = 32,000** |
| Judges per query | **2** fixed primary judges for all 400 products |
| Judge independence | Neither primary judge may be the **query author** |
| Coverage | Every `(query_id, product_id)` pair exactly once per judge slot |
| Grades | Integer **0**, **1**, or **2** (JSON number, not string) |
| Rationale | Required non-blank for grades **1** and **2**; may be empty for primary **0** |
| `provenance` | literal `human_manual` |
| `product_id` | Lowercase canonical **UUID** present in frozen corpus—not Khaadi SKU |

Obtain valid `product_id` values from the frozen corpus JSONL (`product_id` field per record).

Judgment line schema (six keys, no extras):

| Field | Rule |
| --- | --- |
| `query_id` | Frozen `TXT-Q-####` |
| `product_id` | Corpus UUID |
| `judge_id` | Opaque alias |
| `grade` | 0 / 1 / 2 |
| `rationale` | See above |
| `provenance` | `human_manual` |

Illustration only:  
[configs/examples/eval_text_v1/SCHEMA-ILLUSTRATION-ONLY.judgment.jsonl](../configs/examples/eval_text_v1/SCHEMA-ILLUSTRATION-ONLY.judgment.jsonl)

**Adjudication** (`human_adjudications.jsonl`) — only for pairs where the two primaries disagree:

| Field | Rule |
| --- | --- |
| `query_id`, `product_id` | Disputed pair |
| `adjudicator_id` | Third human; not either primary judge |
| `grade`, `rationale`, `provenance` | Final grade; rationale always non-blank |

Query author **may** adjudicate (counted/disclosed). Prefer an uninvolved adjudicator.

Each split must retain at least one **answerable** query (≥1 product with grade ≥1 after consensus)—do not invent relevance.

Judgment workload tracker:  
`configs/examples/eval_text_v1/judgment_progress_tracker.template.csv`

---

## 6. Label freeze commands

```powershell
python scripts/prepare_text_evaluation.py freeze-labels `
  --judgments data/eval_text_v1/human_judgments.jsonl `
  --adjudications data/eval_text_v1/human_adjudications.jsonl

# Omit --adjudications only if there are zero primary disagreements

python scripts/prepare_text_evaluation.py verify
```

Update [reports/eval_text_v1_readiness.md](../reports/eval_text_v1_readiness.md) is regenerated by tooling when `verify` / readiness paths run—expect **dataset ready: YES** before any FTS work.

### Phase 1B exit: full EVAL-TEXT-V1 dataset

- [ ] 32,000 primary judgments validated  
- [ ] All disagreements adjudicated  
- [ ] `freeze-labels` + full `verify` succeed  
- [ ] Frozen qrels bound to corpus + protocol + query checksums  
- [ ] **Still no metrics execution** in labeling tooling—that comes with retriever evaluation  

---

## 7. What happens next (do not start early)

Only after Phase 1B:

1. Accept **ADR-ML-002** (PostgreSQL FTS configuration).  
2. Implement `src/sahulat_text/retrievers/lexical/` + search migration.  
3. Run Baseline **A** on frozen **test** split for headline metrics; **dev** for tuning per protocol.  

See [repository-structure.md](architecture/repository-structure.md) Phase 2 order.

---

## 8. Common validation failures

| Symptom | Likely cause |
| --- | --- |
| `intent-group leakage between dev and test` | Same `TXT-I-####` in both splits |
| `duplicate query identity or normalized text` | Reused ID or NFKC/casefold duplicate text |
| `insufficient split/query-class coverage` | Fewer than 20 queries in a split or missing class in a split |
| `insufficient independent intent-group coverage` | Fewer than 20 distinct `TXT-I-####` in a split |
| `product_id is outside the frozen corpus` | SKU or wrong UUID |
| `query author cannot be a primary judge` | Author listed as judge |
| `incomplete exhaustive two-judge coverage` | Missing query×product rows or wrong judge count |
| `unresolved human disagreement` | Disagreement without adjudication row |
| `collection/receipt drift` | Edited JSONL without matching `.import.json` |

---

## 9. Sign-off (coordinator attestation)

Record separately (not in frozen JSONL):

- [ ] Genuine human authorship confirmed for all queries and grades  
- [ ] English semantic scope confirmed  
- [ ] Authors/judges not exposed to retrieval outputs for these queries  
- [ ] Test-label access restricted until retriever configs frozen  
- [ ] Identity maps (alias → person) stored privately  

Date: __________  
Coordinator: __________  
