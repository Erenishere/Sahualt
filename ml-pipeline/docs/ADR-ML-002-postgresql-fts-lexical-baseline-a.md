# ADR-ML-002: PostgreSQL FTS lexical Baseline A (prototype)

Status: **DRAFT — parallel prototype track; not official benchmark execution.**  
Date: 2026-09-26  
Depends on: accepted ADR-ML-004 (`product-text-v1`), frozen PRODUCT-TEXT-V1 corpus registry.

## Context

Sahulat Text Retrieval V1 requires **Baseline A** lexical retrieval using **PostgreSQL
full-text search**, aligned with the FYP proposal. Human **EVAL-TEXT-V1** labels are not
frozen yet; the protocol blocks using unfrozen queries and treating retrieval as official
benchmark evidence until label freeze.

Engineering may still implement and test FTS in an **isolated prototype** using **synthetic
catalogues and developer queries only**, without contaminating human query/label collection.

## Decision

1. **Engine:** PostgreSQL FTS (not BM25-in-Python, not Elasticsearch for V1 Baseline A).
2. **Schema:** new `search` schema, table `search.product_text_lexical_v1` (Migration 002).
3. **Document source:** searchable text is the canonical `product-text-v1` rendered `text`
   field (Name / Description / optional Color lines), not raw Listing/Inventory fields.
4. **Configuration (prototype v1):**
   - `text_search_config`: `english`
   - Query parser: `websearch_to_tsquery('english', query)`
   - Rank: `ts_rank_cd(document_tsvector, query)`
   - Stored vector: `GENERATED ALWAYS AS (to_tsvector('english', searchable_text)) STORED`
5. **Retriever contract:** implement `sahulat_text.TextRetriever` as
   `PostgresLexicalRetriever` with `retriever_id = postgresql-fts-lexical-prototype-v1`.
6. **Index identity:** `index_version` includes corpus SHA-256 and migration id
   (`20260926_002_search_lexical_v1`).

## Prototype boundaries (mandatory until label freeze)

| Allowed | Forbidden |
| --- | --- |
| Synthetic toy catalogues (unit/integration tests) | Official EVAL-TEXT-V1 query set |
| Developer queries like `"red shirt"` on toy data | Ranking inspection on frozen 400-product corpus for tuning |
| Feature branch / prototype merge prep | Claiming official Baseline A benchmark numbers |
| Rebuilding index from verified corpus **bytes** in controlled CI later | Exposing retrieval output to query authors/judges |

After **label freeze**, a separate gate promotes configuration, merges official paths, runs
**dev** tuning then **test** evaluation once per protocol.

## Consequences

- Adds Migration `20260926_002_search_lexical_v1.sql` (does not alter Catalog Core V1).
- Lexical code lives under `src/sahulat_text/retrievers/lexical/`.
- No dense, RRF, HTTP text route, or EVAL-TEXT-V1 metrics runner in this ADR.

## Alternatives rejected

- **rank_bm25 / Whoosh-only Baseline A:** proposal mandates PostgreSQL FTS; interim BM25 would
  require a separate explicit ADR amendment.
- **Indexing only in-application without SQL FTS:** would not satisfy proposal Baseline A or
  reuse PostgreSQL operational tooling.

## Engineering freeze (2026-09-26)

Prototype implementation for Baseline A is **complete and frozen** under
[ENGINEERING-TEXT-PROTOTYPE-V1](ENGINEERING-TEXT-PROTOTYPE-V1.md). This ADR remains **DRAFT**;
no official EVAL-TEXT-V1 benchmark execution or production config lock until human label freeze.
