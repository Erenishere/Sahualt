# ADR-ML-003: Dense text retrieval prototype (Baseline B)

Status: **DRAFT — prototype track; not production encoder selection.**  
Date: 2026-09-26  
Depends on: ADR-ML-004 (`product-text-v1`), ADR-ML-002 draft (lexical prototype).

## Context

Baseline B requires semantic product-text retrieval. Human **EVAL-TEXT-V1** labels are
not frozen; official dense benchmark execution remains blocked. Engineering still needs a
**TextRetriever**-compatible dense branch for synthetic validation and future RRF (Baseline D).

## Decision (prototype v1 only)

| Topic | Prototype choice |
| --- | --- |
| Storage | PostgreSQL **pgvector** column on `search.product_text_dense_v1` |
| Migration | `20260926_003_text_dense_prototype_v1` |
| Vector dimension | **3** (toy encoder only; new migration required for production dim) |
| Encoder (now) | `ToyTextEncoder` — deterministic keyword axes, **no model download** |
| Encoder (later) | `RealTextEncoder` behind same `TextEncoder` protocol; separate ADR amendment |
| Candidate (future) | BGE-M3 or validated alternative — **not selected in this ADR** |
| Similarity | Cosine via pgvector `<=>` (exact scan; no HNSW/IVFFlat on toy set) |
| Normalization | L2 unit vectors before insert and query |
| Corpus binding | `corpus_sha256` + `encoder_id` + `encoder_revision` on every row |
| retriever_id | `postgresql-dense-prototype-v1` |

## Prototype restrictions

- Toy catalogue and developer queries only for smoke/integration tests.
- No official EVAL-TEXT-V1 metrics or tuning on frozen queries.
- Full-corpus indexing uses the same infrastructure guards as lexical (blocked once frozen
  query artifacts exist unless coordinator policy changes).
- **No claim** that toy vectors represent production semantic quality.

## Consequences

- Requires `CREATE EXTENSION vector` (host must ship pgvector).
- Dense code isolated under `src/sahulat_text/retrievers/dense/`.
- Hybrid RRF consumes ranked `TextMatch` lists only; no SQL in hybrid layer.

## Not decided (post label freeze)

- Final encoder revision and embedding dimension.
- ANN index type and recall/latency trade-offs at 400+ products.
- Official Baseline B benchmark report.

## Engineering freeze (2026-09-26)

Toy dense prototype (`ToyTextEncoder`, dim 3, exact cosine) is **complete and frozen** under
[ENGINEERING-TEXT-PROTOTYPE-V1](ENGINEERING-TEXT-PROTOTYPE-V1.md). This ADR remains **DRAFT** and
does **not** select a production encoder or claim retrieval accuracy.
