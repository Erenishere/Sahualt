# ADR-DATA-001: Product ingestion and search metadata contract

Status: **Accepted, with ProductVariant addendum, 2026-09-10.**

## Context

Sahulat AI needs one vendor-facing Add Product flow, but product meaning, variant
characteristics, mutable commerce state, and inventory have different lifecycles.
Designing `product-text-v1` directly from the Khaadi CSV would incorrectly make an
evaluation fixture the production contract and could force expensive text re-indexing
after price or stock changes.

The original decision placed Color directly on Product. That conflicts with normal
fashion catalogue behavior: one semantic product can have multiple color/size
variants. This contradiction was discovered before database migrations or canonical
documents existed, so this accepted addendum corrects ownership without invalidating
any built index or evaluation result.

Khaadi is therefore evaluation data only. PostgreSQL is the production system of
record. JSONL is limited to snapshots, offline experiments, and reproducibility
evidence.

## Decision

The backend presents one Add/Edit Product operation and persists five internal
boundaries:

```text
Product              ProductVariant       Listing              Inventory
name                 variant_code         price                on_hand_quantity
description          sku                  currency             reserved_quantity
category_id           color                availability
brand                 size                 status

ProductImage
image identity/location, ordering, upload metadata
optional ProductVariant association
```

`product_id` is generated and unique in production. The ML/search boundary treats it
as an opaque non-empty string so evaluation fixtures can retain source identifiers.
Normal API writes must enforce product identity uniqueness in PostgreSQL.

Every Product has at least one ProductVariant. Products without meaningful variants
use one default variant with `variant_code = default`; optional characteristics such
as Color or Size remain null when unknown. Listing belongs to ProductVariant, and
Inventory belongs to Listing. ProductImage always belongs to Product and may also
reference a ProductVariant for variant-specific imagery.

The ML service never receives an uncommitted vendor form as its source of truth. The
.NET API validates and persists the business records first; only the committed Product
projection, or a reproducible snapshot of it, may enter the canonical builder. Index
updates are idempotent by document checksum, and their delivery mechanism is a later
integration decision.

### Vendor input contract

| Field | Requirement | Validation | Ownership |
| --- | --- | --- | --- |
| `product_name` | Required | Trimmed, non-empty, bounded length | Product |
| `description` | Required | Trimmed, non-empty, bounded length | Product |
| `color` | Optional, recommended | Trimmed controlled/free text; null when unknown | ProductVariant |
| `size` | Optional | Trimmed controlled/free text; null when unknown | ProductVariant |
| `category_id` | Required to publish | Existing controlled category identifier | Product |
| `brand` | Optional | Trimmed vendor-provided value | Product |
| `price` | Required | Decimal, finite, greater than or equal to zero | Listing |
| `currency` | Required | Supported uppercase ISO 4217 code | Listing |
| `availability` | Required | Backend-controlled value; initial values are `in_stock` and `out_of_stock` | Listing |
| `stock_quantity` | Optional | Integer greater than or equal to zero; null means unknown | Inventory |
| `images` | Required to publish | Approved MIME type, decoded-content validation, configured size/count limits; optional variant association | ProductImage |

Draft/publish state and future availability values belong to the backend lifecycle
contract and must not be inferred by ML code. Category and brand may be supplied by a
vendor even though the Khaadi fixture lacks those columns. AI-generated metadata is
forbidden unless a later enrichment policy is explicitly accepted.

### Search and filter ownership

`product-text-v1` contains only stable semantic fields, in this fixed order:

```text
Product Name: {normalized name}
Description: {normalized description}
Color: {deterministic normalized variant colors}       # omitted when none exist
```

Color retains the existing semantic role but is sourced from ProductVariant. The
builder collects colors from the applicable non-archived variants in its committed
Product projection, applies the locked normalization to each value, omits empty
values, removes exact normalized duplicates, and sorts the remaining values by
Unicode code-point order. One color renders as `Color: Blue`; multiple colors render
as one comma-separated line such as `Color: Black, Blue`. No color ontology,
case-folding, synonym expansion, or image-based inference is permitted.

The machine record contains:

```json
{
  "schema_version": "product-text-v1",
  "product_id": "opaque-id",
  "fields": {
    "name": "Embroidered Lawn Shirt",
    "description": "Three piece embroidered lawn suit...",
    "colors": ["Blue"]
  },
  "text": "Product Name: Embroidered Lawn Shirt\nDescription: Three piece embroidered lawn suit...\nColor: Blue",
  "document_checksum": "sha256:..."
}
```

Listing metadata remains a separate projection, for example:

```json
{
  "variant_id": "opaque-variant-id",
  "price": 4990.00,
  "currency": "PKR",
  "availability": "in_stock"
}
```

Inventory remains separate from Listing:

```json
{
  "listing_id": "opaque-listing-id",
  "on_hand_quantity": 12,
  "reserved_quantity": 0
}
```

Price, currency, availability, and inventory quantities never appear in canonical
text. They remain structured Listing/Inventory metadata and become search filters.
Category and brand remain structured Product metadata and may become filters
independently. Size remains structured ProductVariant metadata. These fields are
excluded from `product-text-v1`; adding any of them to semantic text requires a new
document schema version. Images are handled only by the visual pipeline.

### Canonical normalization

The canonical builder must:

1. apply Unicode NFKC normalization;
2. remove Unicode control characters;
3. trim leading and trailing whitespace;
4. collapse repeated whitespace;
5. preserve meaningful punctuation and the original language;
6. omit absent optional fields; and
7. never translate, summarize, generate keywords, insert placeholders, or infer data.

The backend owns input validation and persistence. The canonical builder owns this
retrieval normalization and must apply it deterministically regardless of whether its
input came from PostgreSQL or an evaluation snapshot.

### Version and checksum

The meaning of `product-text-v1` is immutable. Any field, ordering, label, or
normalization change creates `product-text-v2` or a later version and requires a new
FTS index and dense embeddings.

`document_checksum` is SHA-256 over the UTF-8 encoded canonical JSON record excluding
the checksum itself, serialized with sorted object keys, no insignificant whitespace,
and no trailing newline. The payload includes `schema_version`, `product_id`,
normalized `fields`, and rendered `text`. The stored form is `sha256:<lowercase hex>`.

### Change and re-index policy

| Change | Persist | Rebuild `product-text-v1` | Dense re-embed | Other action |
| --- | ---: | ---: | ---: | --- |
| Name | Yes | Yes | Yes | Refresh FTS |
| Description | Yes | Yes | Yes | Refresh FTS |
| Variant color set | Yes | Yes | Yes | Refresh FTS |
| Variant size | Yes | No for v1 | No for v1 | Update structured metadata |
| Category | Yes | No for v1 | No for v1 | Update structured metadata |
| Brand | Yes | No for v1 | No for v1 | Update structured metadata |
| Price/currency | Yes | No | No | Update listing filter data |
| Inventory/availability | Yes | No | No | Update structured filter data |
| Image | Yes | No | No | Run visual indexing policy |
| Product removal | Yes | N/A | N/A | Remove/tombstone all search entries |

Re-index decisions compare the canonical semantic checksum, not the raw update event.
An unchanged checksum must not trigger FTS refresh or dense embedding generation.

### Invalid and duplicate source data

- Missing product ID or name is rejected in production and quarantined in evaluation.
- Production submissions without a description are rejected; evaluation rows follow
  the frozen benchmark missing-data policy and are reported.
- Missing variant color is valid and remains absent; it is never inferred.
- Duplicate fixture rows with the same product ID and identical normalized data are
  deterministically deduplicated and recorded as evidence.
- Duplicate product IDs with conflicting data fail or enter quarantine; the pipeline
  must never choose a winner silently.

## Consequences

Semantic edits and changes to the normalized distinct variant-color set require text
re-indexing and later dense re-embedding. Variant size, Listing, and Inventory edits
remain cheap structured updates. Each Khaadi fixture product maps to one default
variant: source Color maps to ProductVariant Color, Size remains null, and source
Price/Availability map to Listing while Currency and Inventory remain unsupported.
ADR-ML-004 must specify the transformation implementation without changing these
boundaries. PostgreSQL schemas, migrations, API endpoints, and enrichment remain
separate implementation work.
