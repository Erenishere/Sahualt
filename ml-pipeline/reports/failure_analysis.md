# Visual retrieval failure analysis

The complete raw failure records are in
`artifacts/benchmarks/{openclip,fashionclip}/failures.json`; per-query metrics and
ranked products are saved for all 399 queries. Portable copies are saved under
`reports/benchmarks/`. See [reviewed evidence](failure_analysis.json) for image IDs,
top retrieved products and observational annotations.

| Outcome | Count |
| --- | ---: |
| OpenCLIP incorrect P@1 | 114 |
| FashionCLIP incorrect P@1 | 111 |
| Both correct at rank 1 | 271 |
| Only OpenCLIP correct | 14 |
| Only FashionCLIP correct | 17 |
| Both incorrect | 97 |
| Visually reviewed errors per model | 5 |

The broader weak/error lists contain 334 OpenCLIP and 337 FashionCLIP queries.
These include correct rank-one queries with Recall@5 below one; when a product has
more than five relevant gallery images, perfect Recall@5 is impossible. These
counts must not be interpreted as top-one errors or used to claim that FashionCLIP
has worse quality overall.

## Sampling and observations

For each model, review the first five incorrect P@1 queries ordered by image ID.
This deterministic, small qualitative sample is not representative frequency
estimation. Every remaining error is retained as unreviewed; no scores or splits
are changed. The reviewed sample contains six distinct query IDs, with overlap
between models. Observed cases:

* `ACA231001/image_1.jpg`: OpenCLIP retrieves `ALA230827/image_2.jpg`, a different
  outfit with a similar long-top/scarf silhouette. FashionCLIP retrieves
  `BLK231001/image_1.jpg`, a navy/white floral outfit whose pattern and scarf details
  differ. The latter is a visible similar-color/pattern confusion.
* `ACA231003/image_1.jpg`: OpenCLIP retrieves `BK231002/image_5.jpg` (dark fabric,
  small repeated motifs, rear pose). FashionCLIP retrieves `LLA230913/image_4.jpg`
  (dark fabric and rear pose but white chevrons). Ground-truth designs differ.
* `ACA231006/image_0.jpg` (FashionCLIP): a light grey/blue dragonfly-print outfit
  retrieves royal-blue striped ornamentation in `ALK231017/image_3.jpg` with
  similar full-length front framing and scarf presentation.
* `ACA231008/image_0.jpg`: both retrieve `EET235134/image_3.jpg`; both frames are
  close portraits, despite contrasting light tree-motif versus dark bright-floral
  garments. Model/person dominance is a **hypothesis**, not a verified cause.
* `AJ230603/image_0.jpg`: both retrieve `ALA230801/image_0.jpg`; warm-toned close
  upper-body views have different neckline and print details. Composition influence
  again remains untested.
* `AJ230604/image_2.jpg` (OpenCLIP): a red outfit retrieves the orange/yellow
  `AJ230603/image_2.jpg`; scarf silhouette and full-length framing are similar,
  while garment colors and designs differ.

No OCR, person identification, attention attribution, crop ablation or background
ablation was performed. We do not assign unsupported causes such as background
interference, low quality, front/back confusion or insufficient catalogue views.
The exact audit does not detect all near duplicates or guarantee absence of
pretraining overlap. These limitations remain explicit.

## Implication

Both encoders still confuse visually similar products; neither is an exact SKU
recognizer. The three-query net advantage for FashionCLIP should be interpreted
alongside paired uncertainty and measured latency in ADR-ML-001. More extensive
human review and a genuinely held-out customer-photo/catalogue evaluation should
precede any decision to fine-tune. No new ML phase was implemented here.
