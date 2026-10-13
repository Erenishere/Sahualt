# Visual model comparison

Actual EVAL-VISUAL-V1 measurements.

Frozen split: `28b63cb56b42325cd6d6a51cc9faa82ea652c89dbb24ddd2c9046289fbadc767`.

| Metric | OpenCLIP | FashionCLIP | Numerical winner |
| --- | ---: | ---: | --- |
| map_at_5 | 0.474951 | 0.482251 | FashionCLIP |
| mrr | 0.801395 | 0.809137 | FashionCLIP |
| ndcg_at_5 | 0.575179 | 0.584638 | FashionCLIP |
| precision_at_1 | 0.714286 | 0.721805 | FashionCLIP |
| precision_at_5 | 0.383960 | 0.394486 | FashionCLIP |
| recall_at_5 | 0.514757 | 0.521816 | FashionCLIP |
| Query embedding latency (mean ms) | 170.844173 | 199.611783 | OpenCLIP |
| Search latency (mean ms) | 4.430072 | 4.834845 | OpenCLIP |
| Embedding dimension | 512.000000 | 512.000000 | — |

Numerical winners are descriptive, not significance claims. This comparison command does not select a model automatically. ADR-ML-001 selects OpenCLIP for the initial CPU deployment after reviewing quality, paired uncertainty, latency, operational evidence and limitations.

Same recorded timing environment: True. Background system load and cache state still affect timings.

Both candidates use ViT-B/32. OpenCLIP uses its native implementation; FashionCLIP uses the Transformers vision projection. Each uses checkpoint-specific preprocessing. Khaadi same-product quality does not establish general commerce or user-photo performance. Model loading includes cache/download effects; compare warm inference separately.

Paired product-cluster bootstrap, 2,000 resamples, seed 42. Differences below are FashionCLIP minus OpenCLIP; intervals describe sampling uncertainty within this dataset, not catalogue generalization.

* precision_at_1: delta 0.007519, 95% interval [-0.020050, 0.035088].
* map_at_5: delta 0.007300, 95% interval [-0.005126, 0.019082].
