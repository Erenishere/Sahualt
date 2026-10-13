# ADR-ML-001: Visual encoder selection

Status: **Accepted for initial CPU serving, 2026-09-06.**

## Context

Sahulat AI needs query-image to unique-product retrieval from a multi-view
catalogue. Encoder choice affects retrieval quality, inference cost, operations
and which catalogue vectors must be regenerated.

## Candidates

OpenCLIP ViT-B/32 LAION-2B and FashionCLIP 2.0. Exact immutable checkpoint revisions
are frozen in `configs/eval_visual_v1.yaml`. No fine-tuning is permitted this phase.

## Evaluation

See [EVAL-VISUAL-V1](EVAL-VISUAL-V1.md). Both must use the same audited dataset,
frozen split, relevance, metric code and timing definitions. The historical split
was unavailable in the initially empty workspace; this new split cannot be used
to claim reproduction of the supplied historical scores.

## Results

Both candidates completed EVAL-VISUAL-V1 with the same dataset, audit, split,
source hash, package versions and CPU thread count. Actual results:

| Metric | OpenCLIP | FashionCLIP |
| --- | ---: | ---: |
| P@1 | 0.714286 | 0.721805 |
| P@5 | 0.383960 | 0.394486 |
| Recall@5 | 0.514757 | 0.521816 |
| MRR | 0.801395 | 0.809137 |
| mAP@5 | 0.474951 | 0.482251 |
| nDCG@5 | 0.575179 | 0.584638 |
| Mean query embedding, ms | 170.844 | 199.612 |
| Query embedding p95, ms | 206.699 | 252.909 |
| Mean full-gallery search, ms | 4.430 | 4.835 |
| Mean end-to-end retrieval, ms | 176.276 | 205.673 |
| Gallery embedding total, seconds | 188.761 | 210.004 |
| Model load, cached weights, seconds | 7.194 | 3.046 |
| Embedding dimension | 512 | 512 |
| Indexed gallery vectors | 1,694 | 1,694 |

See [machine-readable comparison](../reports/visual_model_comparison.json) and
[failure analysis](../reports/failure_analysis.md). FashionCLIP gets 288/399 P@1
queries correct versus 285/399 for OpenCLIP: 271 both correct, 17 FashionCLIP-only,
14 OpenCLIP-only, and 97 both wrong. A deterministic first-five-error review for
each model found similar-pattern/garment confusion and portrait-heavy examples.
Only observed similarities are labelled; suspected composition effects are not
claimed as established causes. All failures remain available for further review.

Paired product-cluster bootstrap (2,000 resamples, seed 42), FashionCLIP minus
OpenCLIP: P@1 difference 0.007519, 95% interval [-0.020050, 0.035088]; mAP@5
difference 0.007300, interval [-0.005126, 0.019082]. These intervals include zero.
This does **not** prove equivalence; no predeclared equivalence margin was used.
No historical or synthetic values are included above.

## Operational comparison

Both candidates are ViT-B/32 with 512-D projected image features. OpenCLIP uses
native OpenCLIP preprocessing/model APIs; FashionCLIP uses the Transformers vision
projection and its checkpoint image processor. Model initialization is once per
process; inference is batched for indexing and normalized on both paths. Local
exact cosine retrieval avoids database dependencies at this stage. Weight
downloads are cached, not committed. Compare measured warm latencies separately
from downloads/startup; host memory and deployment stability require further evidence.

## Decision

Select **OpenCLIP ViT-B/32 LAION-2B** as the initial visual serving model for the
current CPU deployment. Keep FashionCLIP available through `VISUAL_MODEL=fashionclip`.
The default configuration remains `VISUAL_MODEL=openclip`. This decision is scoped
to this phase and environment, not a universal ranking of the encoders.

## Reason

FashionCLIP leads numerically on all six quality metrics, but the net P@1 gain is
three queries (0.75 percentage points), and the measured P@1/mAP advantage is
uncertain at this sample size. OpenCLIP's mean warm query embedding time is about
14.4% lower and its gallery embedding pass about 10.1% shorter in these runs.
We accept the small observed quality trade-off in favor of the faster measured
serving path. FashionCLIP has a faster cached startup; loading once per lifecycle
reduces that advantage for sustained serving. Both adapters are small and tested;
we do not claim a quantified dependency-footprint advantage for either.

Both full runs and real-model consistency tests completed without skipped queries
or runtime failures after environment setup. This is operational evidence, not a
long-duration stability test. Memory consumption was not benchmarked on this CPU
host, and GPU latency is unmeasured. Runs were sequential on the same eight-thread
CPU, but background load, thermals and cache state were not experimentally controlled.
Recheck latency on the actual deployment host before setting an SLO.

Khaadi catalogue views do not establish cross-category or customer-photo
generalization for either candidate. The reviewed failures do not justify
fine-tuning yet. A broader held-out dataset and more complete causal failure
analysis are required before proposing training or claiming robust model superiority.

## Consequences

Switching model, weight revision or preprocessing/dependency identity requires a
complete catalogue re-embedding and replacement index. Service startup rejects
incompatible indexes even if dimensions match. Fine-tuning and downstream text,
hybrid, multimodal and voice phases remain out of scope.
