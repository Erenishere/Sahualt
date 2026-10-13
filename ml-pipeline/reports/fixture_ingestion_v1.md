# Fixture Ingestion V1

Status: **GREEN**  
Importer: `fixture-ingestion-v1`  
Source: `data/raw/khaadi/Khaadi_Data/khaadi_data.csv`  
Source SHA-256: `bbb0a5b3eed1bfbe6dd7c2add33cff7d0420db82e1d9f961ecdd61e1d391119e`  
Semantic checksum: `0a686d197ec1bdac3ea49bfe0a8ee9487db95d6c6967d72c909d5cc490eab900`  
Import result checksum: `6e5673fab2823ed72d9415d288aae1b9ff180c842baa79863b885081ded5f9a2`

## Authority and disposition

- Dataset version: `1`
- Gate 1: `khaadi-contract-mapping-v2`
- DB contract: `DB-CONTRACT-V1`
- Source products: 400
- Importable: 400
- Quarantined: 0
- Rejected: 0

## Canonical mapping

| Source | Destination |
| --- | --- |
| ID | `catalog.product_external_refs.external_product_id` |
| Product Name | `catalog.products.name` |
| Product Description | `catalog.products.description` |
| Color | `catalog.product_variants.color` |
| Price | `catalog.listings.price` |
| Availability | `catalog.listings.availability` |
| EVAL-VISUAL-V1 retained image | `catalog.product_images + catalog.image_external_refs` |

Availability uses the explicitly frozen fixture alias `In Stock -> in_stock`.
This is protocol normalization, not inferred stock quantity.

## Imported state

- Products: 400
- Default variants: 400
- Draft listings: 400
- Inventory rows: 0
- Product images: 2093
- Product external refs: 400
- Image external refs: 2093

Images follow locked Visual V1: 2,109 manifest records, 2,093 retained/imported,
and 16 duplicate/conflicting records excluded. Images are product-level because the
source does not assert variant-specific ownership.

## Parity and idempotency

- Field parity: **GREEN**
- Idempotency: **GREEN**
- Second-run inserts: 0 across Vendor, Product, Variant, Listing, Image, and external refs
- Outbox events emitted: 0

All required semantic fields equal the normalized audited source. `brand_name`,
`category_id`, Size, Currency, and Inventory remain NULL/absent. Generated UUIDs and
timestamps are excluded from the semantic checksum.

## Limitations

- The fixture vendor is synthetic structural infrastructure, not dataset metadata.
- Currency, Size, Brand, Category, and numeric Stock are not supplied or inferred.
- Only the 2,093 images retained by locked Visual V1 are imported; 16 duplicate/conflicting images remain excluded.
- The current local database login is administrative; runtime least-privilege roles remain a later platform task.

Evidence checksum: `sha256:ee817a152cb091515d62c499a8bba628f0f6c9ad3256c9a8e9e7f7da8caaef8d`.
