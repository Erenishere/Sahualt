# Executed dataset audit

Source: `usman8/khaadis-clothes-data-with-images`, version 1.
Archive checksum and source metadata: [dataset_source.json](dataset_source.json).
Full per-image hashes and exclusions: [dataset_audit.json](dataset_audit.json).

| Count | Executed result |
| --- | ---: |
| CSV product records | 400 |
| Raw image files | 2,109 |
| Retained images | 2,093 |
| Retained products | 400 |
| Within-product exact duplicates removed | 1 |
| Conflicting-label images excluded | 15 |
| Missing / corrupt / unreadable / unsupported images | 0 |
| Missing product IDs / orphan images | 0 |
| New-split query images | 399 |
| New-split gallery images | 1,694 |
| Products with queries | 399 |
| Gallery-only singleton products | 1 |

The singleton is `EKT22320B`. It remains a gallery distractor; it was not excluded
for being difficult. Query and gallery together account for every retained image.
No model results were consulted to select images or exclusions.

Split: [eval_visual_v1_split.json](eval_visual_v1_split.json), SHA-256
`28b63cb56b42325cd6d6a51cc9faa82ea652c89dbb24ddd2c9046289fbadc767`.
This is the canonical new EVAL-VISUAL-V1 split. The historical 443/1,649 split was
not present and is not claimed to have been reproduced. Exact-audit counts agree
with the historical counts; that alone does not prove an identical historical audit.
