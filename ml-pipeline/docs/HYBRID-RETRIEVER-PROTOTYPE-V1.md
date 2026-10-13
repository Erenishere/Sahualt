# Hybrid RRF retriever prototype V1 (engineering track)

Status: **prototype only** — not official Baseline D benchmark evidence.

## Prerequisites

Both lexical and dense prototype indexes for the same `corpus_sha256`:

```powershell
python scripts/build_lexical_index_prototype.py --toy
python scripts/build_dense_index_prototype.py --toy
```

## Smoke

```powershell
python scripts/smoke_hybrid_retriever_prototype.py --query "red shirt" --top-k 3
```

## Code map

| Module | Role |
| --- | --- |
| `rank_fusion.py` | Pure `reciprocal_rank_fusion` |
| `retriever.py` | `HybridRRFRetriever(lexical, dense, config)` |
| `config.py` | `rrf_k`, branch source labels, `branch_depth` |

Hybrid layer has **no SQL** — only `TextRetriever.search` → RRF → `TextMatch[]`.

## Stop line

Official EVAL-TEXT-V1 metrics remain **blocked until human label freeze**.
