# Dense retriever prototype V1 (engineering track)

Status: **prototype only** — [ADR-ML-003 draft](ADR-ML-003-dense-text-retrieval-prototype.md).  
Not official Baseline B benchmark evidence.

## Prerequisites

```powershell
python scripts/apply_database_migrations.py
python scripts/apply_search_lexical_migration.py   # optional for dense-only experiments
python scripts/apply_search_dense_migration.py     # requires pgvector on PostgreSQL
```

## Index + smoke (toy)

```powershell
python scripts/build_dense_index_prototype.py --toy
python scripts/smoke_dense_retriever_prototype.py --query "red shirt" --top-k 3
```

Toy encoder uses keyword axes (`red`, `blue`, `black`) → 3-D unit vectors.  
Default toy corpus SHA-256: 64× `b`.

## Code map

| Module | Role |
| --- | --- |
| `encoder.py` | `TextEncoder` protocol + `ToyTextEncoder` |
| `repository.py` | `rebuild_dense_index`, `records_from_searchable_texts` |
| `retriever.py` | `PostgresDenseRetriever` (`TextRetriever`) |

## Next

Hybrid: [HYBRID-RETRIEVER-PROTOTYPE-V1.md](HYBRID-RETRIEVER-PROTOTYPE-V1.md).
