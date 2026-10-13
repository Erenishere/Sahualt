# openclip — EVAL-VISUAL-V1

Split: `28b63cb56b42325cd6d6a51cc9faa82ea652c89dbb24ddd2c9046289fbadc767` (new-split-not-historical).

| Metric | Value |
| --- | ---: |
| precision_at_1 | 0.714286 |
| precision_at_5 | 0.383960 |
| recall_at_5 | 0.514757 |
| mrr | 0.801395 |
| map_at_5 | 0.474951 |
| ndcg_at_5 | 0.575179 |

Indexed vectors: 1694; dimension: 512.
Device: cpu.

Warm query: validation, decode, preprocessing, transfer, inference; search: full exact ranking; e2e includes MAX aggregation, excludes HTTP. Gallery per-image samples are batch-amortized, not serial observations. Model loading may include downloads; warmup excluded from embedding totals.

See results.json for latency distributions and reproducibility metadata.
Failures/weak queries for manual review: 334. Categories remain empty until supported by visual inspection.
