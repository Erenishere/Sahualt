# EVAL-VISUAL-V1

This is a **new evaluation**, not a reproduction of the historical Khaadi split.
The original split, OpenCLIP weight tag, dependency versions and exact metric
formulas were not supplied. The historical retained count also exceeds the sum of
its query and gallery counts by one. Historical scores are not used in code.

## Dataset and provenance

Source: [usman8/khaadis-clothes-data-with-images](https://www.kaggle.com/datasets/usman8/khaadis-clothes-data-with-images),
public dataset version 1. The downloaded archive contains 400 CSV product records
and 2,109 image files. The importer verifies archive SHA-256
`f268adbd70a165d1c1ed820ce68968aa6e4954581eb44496c9b508b813c3064e`.
See `data/khaadi/source.json` for the import record and `reports/dataset_audit.json`
for the executed audit when available. Never infer product ground truth from
visual similarity: the importer uses the CSV ID and validates its image folder.

Executed audit: 2,093 retained images across 400 products; one within-product
exact duplicate removed and all 15 cross-product conflicting-label images excluded.
No missing, unreadable, corrupt or invalid-format images were found. The new split
contains 399 queries and 1,694 gallery images, with 399 query products. `EKT22320B`
has only one retained image and is gallery-only. See the saved split in
`reports/eval_visual_v1_split.json`. This agrees with the historical audit counts,
but it does not establish equivalence of duplicate policy or query/gallery split.

## Validation and exclusions

The YAML freezes byte, pixel and dimension limits, allowed decoded formats,
EXIF orientation correction, and RGB conversion. Every manifest row is counted.
Missing/invalid IDs, unsafe paths, missing/unreadable/corrupt/unsupported images
are reported and excluded. Ambiguous duplicate image IDs stop the operation.

SHA-256 is calculated on file bytes and oriented decoded RGB pixels including
dimensions. Identical images with conflicting product labels are **all** excluded.
For exact within-product duplicates, only the lexicographically first image ID is
retained. These rules operate before splitting and do not depend on model scores.
No OCR, enhancement, perceptual near-duplicate exclusions or hard-query removal.
Lossy recompressions and near-identical poses may remain; exact hashing does not
establish the absence of perceptual leakage or pretrained training-set overlap.

## Split and freezing

For each product, order audited images by SHA-256 of `seed:image_id`, then image ID.
Seed is 42. Query count is `min(n-1, max(1, floor(n*0.2)))`; singleton products go
only into the gallery and are listed separately. Thus each query has at least one
same-product gallery image. Gallery-only singletons remain distractors.

`freeze-eval` writes query/gallery IDs and hashes exactly once. Re-running it
validates the existing artifact; it will not replace an incompatible split.
Benchmarks recompute the full audit and fail if image content, metadata, exclusions,
protocol or split changed. The split fingerprints the complete audit, including
exclusions. Relocating dataset/config files does not change the protocol hash.
Both models must consume the exact same split artifact. Save the protocol, audit
and split with every result. Use a new protocol version for methodological changes.
There is no training split or fine-tuning in this phase.

## Relevance and metrics

`relevant = query.product_id == gallery_image.product_id`.
Metrics are computed at the **image level** and macro-averaged over all queries.
Queries are weighted equally; products with more queries can carry more weight.
Product-level results are separately MAX-aggregated for application responses.

With binary relevance `rel_i`, total relevant gallery images `R`, and rank starting
at 1:

* P@K = sum(rel_1..rel_K) / K, even if the gallery is smaller than K.
* Recall@K = sum(rel_1..rel_K) / R.
* RR = 1 / first relevant rank, using the **full gallery**, or zero if none.
* AP@K = sum(P@i * rel_i, i=1..K) / min(K, R).
* DCG@K = sum(rel_i / log2(i+1), i=1..K).
* nDCG@K = DCG@K divided by ideal DCG for min(K, R) relevant hits.

Report P@1, P@5, Recall@5, MRR, mAP@5 and nDCG@5. Zero-relevance metric functions
return zero, but the benchmark split prohibits zero-relevance queries. Full exact
normalized float32 inner-product search ranks higher scores first. Ties use image
ID ascending. This is cosine similarity because **both** vector sides are L2-normalized.

## Candidates and inference

* OpenCLIP ViT-B/32 with LAION-2B `s34B-b79K` weights, repository
  `laion/CLIP-ViT-B-32-laion2B-s34B-b79K`, revision
  `1a25a446712ba5ee05982a381eed697ef9b435cf`.
* FashionCLIP 2.0, repository `patrickjohncyh/fashion-clip`, revision
  `7e3ba62ce16b379a1ab479346b66f192e76f51b7`.

The OpenCLIP baseline uses the base checkpoint identified by the FashionCLIP 2.0
publisher. This is an explicit baseline choice, not an assertion about the
historical OpenCLIP experiment. Publisher references:
[FashionCLIP model card](https://huggingface.co/patrickjohncyh/fashion-clip),
[OpenCLIP implementation](https://github.com/mlfoundations/open_clip/tree/v3.3.0).

Each model uses its own pinned preprocessing configuration for gallery and query.
Both run FP32, eval mode, gradients disabled and inference mode; seeds and
deterministic PyTorch algorithms are set. No training, augmentation or tuning.
The frozen batch size is 16; decode workers default to zero; two queries warm up
the encoder. Device selection is CUDA, MPS, XPU then CPU, or explicitly configured.
Different hardware/library versions can still cause numerical changes.

## Timing and metadata

Device work is synchronized for timings. Model load timing includes imports,
checkpoint loading and downloads on a cold cache. Gallery timing includes bounded
batch image validation/decoding, preprocessing, transfers, inference and normalization.
Batch time divided by batch size is explicitly labelled **amortized**, not measured
serial per-image latency. Query timing measures each image serially including
validation and decoding. Means, medians, p50 and p95 are reported.

Search timing includes full exact ranking required for MRR. End-to-end timing adds
product MAX aggregation to query embedding and full search, excluding HTTP and model
startup. It is a benchmark workload; production adaptive top-K search can differ.
Raw per-query latencies are saved. GPU peak allocated bytes are recorded where CUDA
is available; absence of that field is not a zero-memory claim. Host RSS and
cross-device memory comparisons are not presently measured.

Record timestamp, Git commit/dirty state if available, package/source hashes,
Python/ML versions, device, GPU when available, seed, dataset version, split and
protocol fingerprints, weight revisions, preprocessing identity and all metrics.
No Git repository means commit is null, with source content hash as fallback.

## Failure analysis and selection

All P@1 errors and queries with Recall@5 below one are saved in `failures.json`
with query IDs, top images/products and empty manual review fields. A reviewer may
assign the requested visual categories only with supporting image evidence.
Recall@5 can be below one simply because R > 5; this is not by itself a model error.
Do not filter or relabel the benchmark based on this review.

Compare quality, warm latency, memory, dependencies, operational stability and
catalogue generalization. Small numerical differences do not demonstrate a robust
winner. A final production decision belongs in ADR-ML-001, after both actual runs
and failure review. Khaadi catalogue-view retrieval alone cannot establish
user-photo or broad-commerce generalization.
