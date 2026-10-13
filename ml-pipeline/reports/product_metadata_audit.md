# Khaadi contract-mapping metadata audit

Gate 1 status: **GREEN**.

Khaadi is an evaluation fixture. PostgreSQL remains the production source of truth,
and no missing Product, ProductVariant, Listing, or Inventory attribute was inferred.
Each Khaadi product maps to one default variant. Price and availability are
audited only as structured Listing metadata and are excluded from canonical text.

## Source identity

- CSV: `data/raw/khaadi/Khaadi_Data/khaadi_data.csv`
- SHA-256: `bbb0a5b3eed1bfbe6dd7c2add33cff7d0420db82e1d9f961ecdd61e1d391119e`
- Encoding: `utf-8`; BOM: `false`
- Delimiter: `,`; quote: `"`
- Physical rows excluding header: **400** (401 lines including header)
- Parsed rows: **400**
- Exact columns: `ID`, `Product Name`, `Product Description`, `Price`, `Availability`, `Color`, `Img Path`, `Product Link`

The image manifest is an image-level artifact keyed by CSV product ID: 2,109 image records, 400 product IDs, and product-ID sets match = **true**.

The source metadata identifies the acquisition provenance and declares 400 product records; parsed-count match = **true**.

## Source-to-production mapping

| Khaadi field | Production owner | Canonical use |
| --- | --- | --- |
| ID | Product identity | Required opaque product_id |
| Product Name | Product | Required product-text-v1 field |
| Product Description | Product | Required product-text-v1 field |
| Color | ProductVariant | Optional product-text-v1 variant-color input when present |
| Price | Listing | Structured metadata only; excluded from canonical text |
| Availability | Listing | Structured metadata only; excluded from canonical text |
| Img Path | ProductImage | Evaluation image linkage only; excluded from canonical text |
| Product Link | Fixture provenance | Evaluation provenance only; excluded from production contract |

Currency, stock quantity, brand, category, tags, materials, gender, and product
type are **UNSUPPORTED BY FIXTURE** and remain missing. Category and brand remain
valid vendor-provided production fields; they are not inferred from Khaadi.

## Field quality

Distinct counts and lengths use usable values. p95 length uses nearest-rank.

| Field | Rows | Null | Blank | Whitespace-only | Usable | Coverage | Distinct raw / normalized | Length min / median / p95 / max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| ID | 400 | 0 | 0 | 0 | 400 | 100.00% | 400 / 400 | 8 / 9.0 / 10 / 10 |
| Product Name | 400 | 0 | 0 | 0 | 400 | 100.00% | 83 / 83 | 5 / 15.0 / 21 / 43 |
| Product Description | 400 | 0 | 0 | 0 | 400 | 100.00% | 128 / 128 | 5 / 29.0 / 52 / 57 |
| Price | 400 | 0 | 0 | 0 | 400 | 100.00% | 55 / 55 | n/a |
| Availability | 400 | 0 | 0 | 0 | 400 | 100.00% | 1 / 1 | 8 / 8.0 / 8 / 8 |
| Color | 400 | 0 | 0 | 0 | 400 | 100.00% | 29 / 29 | 3 / 5.0 / 9 / 9 |
| Img Path | 400 | 0 | 0 | 0 | 400 | 100.00% | 400 / 400 | 15 / 16.0 / 17 / 17 |
| Product Link | 400 | 0 | 0 | 0 | 400 | 100.00% | 400 / 400 | 52 / 62.0 / 69 / 91 |

### Duplicate, placeholder, and sample evidence

| Field | Duplicate groups | Duplicate rows beyond first | Placeholder values | Representative samples |
| --- | ---: | ---: | ---: | --- |
| ID | 0 | 0 | 0 | ALK231009; BLK231004; ACA231008 |
| Product Name | 43 | 317 | 0 | Fabrics 3 Piece Suit; Fabrics 2 Piece; Classic Kurta |
| Product Description | 87 | 272 | 0 | Printed Light Khaddar \| Top Bottoms Dupatta; Printed Embroidered Light Khaddar \| Top Bottoms Dupatta; Printed Cambric \| Top Bottoms Dupatta |
| Price | 38 | 345 | 0 | 3490; 4290; 3990 |
| Availability | 1 | 399 | 0 | In Stock |
| Color | 24 | 371 | 0 | NAVY; OLIVE; BEIGE |
| Img Path | 0 | 0 | 0 | images\ALK231009; images\BLK231004; images\ACA231008 |
| Product Link | 0 | 0 | 0 | https://pk.khaadi.com/fabrics-3-piece-suit-alk231009-1001785332.html; https://pk.khaadi.com/fabrics-3-piece-suit-blk231004-1001786404.html; https://pk.khaadi.com/fabrics-3-piece-suit-aca231008-1001785303.html |

### Semantic-field diagnostics

- Product names below 3 normalized characters: **0**
- Product descriptions below 20 normalized characters: **69**
- Product Name exact duplicate groups: **43**
- Product Description exact duplicate groups: **87**
- Meaningful non-ASCII Product Name / Description values: **0 / 0**
- Color coverage: **100.00%**; raw distinct values: **29**; compound/free-text forms: **0**
- Distinct raw colors (no ontology applied): BEIGE, BLACK, BLUE, BROWN, CORAL, D-GREEN, D-PINK, GREEN, GREY, L-GREEN, L-PINK, L-YELLOW, LILAC, MAROON, MULTI, MUSTARD, NAVY, OFF-WHITE, OFF-White, OLIVE, ORANGE, PINK, PURPLE, RED, RUST, TEAL, TURQUOISE, WHITE, YELLOW


## Product ID integrity

- Unique product IDs: **400**
- Missing/blank/whitespace-only IDs: **0 / 0 / 0**
- Duplicate ID groups: **0**
- Identical duplicate groups: **0** (deterministic deduplication candidates)
- Conflicting duplicate groups: **0** (quarantine candidates)
- Valid canonical-document candidates: **400**
- Quarantined product IDs: **0**

## Price (structured Listing metadata only)

Raw values are `CSV string`. Currency inference was **not** performed.

- Parse success: **400/400 (100.00%)**
- Parse failures: **0**; negative: **0**; zero: **0**
- Minimum / median / maximum: **990 / 3690 / 39990**

## Availability (structured Listing metadata only)

Coverage: **100.00%**. No mapping was applied.

| Raw value | Count | Analysis-only candidate |
| --- | ---: | --- |
| In Stock | 400 | `in_stock` |

Mapping assessment: **appears_deterministic_but_requires_explicit_mapping_policy**. Candidate spellings are evidence only and require an explicit mapping policy before ingestion.

## Normalization impact

Normalization was evaluated in analysis mode only: Unicode NFKC, control-character
removal, outer trimming, and repeated-whitespace collapse. No semantic rewriting,
translation, correction, enrichment, or ontology conversion was performed.

| Field | Unicode | Controls | Trim | Whitespace collapse | Any change | Collision groups |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ID | 0 | 0 | 0 | 0 | 0 | 0 |
| Product Name | 0 | 0 | 0 | 0 | 0 | 0 |
| Product Description | 0 | 0 | 0 | 0 | 0 | 0 |
| Price | 0 | 0 | 0 | 0 | 0 | 0 |
| Availability | 0 | 0 | 0 | 0 | 0 | 0 |
| Color | 0 | 0 | 0 | 0 | 0 | 0 |
| Img Path | 0 | 0 | 0 | 0 | 0 | 0 |
| Product Link | 0 | 0 | 0 | 0 | 0 | 0 |

Total normalization collision groups across source fields: **0**.

## Contract fitness

| Field | Classification | Note |
| --- | --- | --- |
| ID | **READY** | Required opaque product_id |
| Product Name | **READY** | Required product-text-v1 field |
| Product Description | **REQUIRES VALIDATION** | Required product-text-v1 field |
| Price | **READY** | Structured metadata only; excluded from canonical text |
| Availability | **REQUIRES VALIDATION** | Structured metadata only; excluded from canonical text |
| Color | **READY** | Optional product-text-v1 variant-color input when present |
| Img Path | **READY** | Evaluation image linkage only; excluded from canonical text |
| Product Link | **READY** | Evaluation provenance only; excluded from production contract |
| Currency | **UNSUPPORTED BY FIXTURE** | Not supplied; no inference permitted |
| Stock quantity | **UNSUPPORTED BY FIXTURE** | Not supplied; no inference permitted |
| Size | **UNSUPPORTED BY FIXTURE** | Not supplied; no inference permitted |
| Brand | **UNSUPPORTED BY FIXTURE** | Not supplied; no inference permitted |
| Category | **UNSUPPORTED BY FIXTURE** | Not supplied; no inference permitted |
| Tags | **UNSUPPORTED BY FIXTURE** | Not supplied; no inference permitted |
| Materials | **UNSUPPORTED BY FIXTURE** | Not supplied; no inference permitted |
| Gender | **UNSUPPORTED BY FIXTURE** | Not supplied; no inference permitted |
| Product type | **UNSUPPORTED BY FIXTURE** | Not supplied; no inference permitted |

## Conclusion

1. One semantic document can be produced for **400** valid product IDs.
2. **0** product IDs require quarantine; **0** rows lack an addressable product ID.
3. Sparse optional fields: **none**.
4. Usable Listing fields: **Price, Availability**; availability aliases still require an explicit mapping policy where noted.
5. Completely absent production fields: **Currency, Stock quantity, Size, Brand, Category, Tags, Materials, Gender, Product type**.
6. Blockers for ADR-ML-004 implementation: **None**.

No generation timestamp is embedded so repeated runs over identical inputs are
byte-for-byte deterministic. Machine-readable counts and evidence are stored in
`artifacts/product_metadata_audit/product_metadata_audit.json`.

Evidence checksum: `sha256:687798fbffad8ec6c2998145ed698b57b8e6a22433df50a95bfa66c84996563e`.
