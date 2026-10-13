# Lexical retriever prototype V1 (engineering track)

Status: **prototype only** — not official EVAL-TEXT-V1 Baseline A evidence.  
ADR: [ADR-ML-002 draft](ADR-ML-002-postgresql-fts-lexical-baseline-a.md)

## Prerequisites

```powershell
python scripts/apply_database_migrations.py
python scripts/apply_search_lexical_migration.py
```

Requires `.env` PostgreSQL settings (same as catalog migrations).

## Index rebuild

**Toy catalogue (default engineering path):**

```powershell
python scripts/build_lexical_index_prototype.py --toy
```

**Frozen product-text-v1 (infrastructure only, blocked after query freeze artifact exists):**

```powershell
python scripts/build_lexical_index_prototype.py `
  --corpus-registry `
  --confirm-infrastructure-index-only
```

## Smoke search (developer queries only)

After `--toy` index build (corpus SHA-256 is 64× `b`):

```powershell
python scripts/smoke_lexical_retriever_prototype.py `
  --query "red shirt" `
  --corpus-sha256 bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb `
  --top-k 3
```

Do not pass EVAL-TEXT-V1 query IDs or frozen benchmark query files.

## Code map

| Path | Role |
| --- | --- |
| `src/sahulat_text/retrievers/lexical/retriever.py` | `PostgresLexicalRetriever` |
| `src/sahulat_text/retrievers/lexical/index.py` | `rebuild_lexical_index` |
| `src/sahulat_text/retrievers/hybrid/rank_fusion.py` | Pure RRF for future Baseline D |

## Next engineering steps

1. Dense Baseline B skeleton (pgvector + encoder ADR).  
2. Wire hybrid retriever to lexical + dense ranks (synthetic tests).  
3. After **label freeze**: officialize config, run protocol metrics on test split once.
