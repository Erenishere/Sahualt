# product-text-v1 canonical build

Gate status: **GREEN**  
ADR: **ADR-ML-004-v1 / ACCEPTED**  
Source contract: `DB-CONTRACT-V1`  
Source migration: `20260910_001_catalog_core_v1`  
Artifact checksum: `sha256:5067202e69fbe0dfd61601e23cfe037a88fcc39a533c923dbdab270e0208e43f`

## Projection and normalization

`CanonicalProductProjection(product_id: UUID, name: str, description: str, colors: tuple[str, ...])` is immutable and fixture-independent.

One read-only PostgreSQL statement loads Product and applicable non-archived ProductVariant colors. Non-archived draft/published/paused Products are included; this is document eligibility, not commercial search eligibility. Archived Products are excluded; malformed required semantics abort the entire build.

Normalization: `product-normalization-v1`, Unicode `15.0.0`; NFKC, Cc controls replaced with spaces, outer trimming and whitespace collapse. Language, punctuation and case are preserved. Colors are normalized, deduplicated and Unicode code-point sorted, then joined with comma + space; free-text values are not split.

Fields: Name -> Description -> optional Color. Missing Color has no text line; machine `colors` is an empty list. No placeholders or inferred metadata.

Excluded: Price, Currency, Availability, Stock, Size, Brand, Category, Vendor, SKU, listing state, images, tags and external IDs. Product UUID is record identity only. Source prose is preserved, not redacted if it happens to mention these concepts.

## Fixture provenance

- Source namespace: `khaadi-v1`
- Source SHA-256: `bbb0a5b3eed1bfbe6dd7c2add33cff7d0420db82e1d9f961ecdd61e1d391119e`
- Gate 1 version: `khaadi-contract-mapping-v2`
- Verified fixture semantic checksum: `0a686d197ec1bdac3ea49bfe0a8ee9487db95d6c6967d72c909d5cc490eab900`

## Measured counts

| Measure | Count |
| --- | ---: |
| canonical products read | 400 |
| documents generated | 400 |
| eligible products | 400 |
| excluded products | 0 |
| multi color products | 0 |
| products with color | 400 |
| products without color | 0 |

## Verification

- DB/document field parity: **GREEN**
- Two independent DB loads/builds, JSONL bytes and artifact checksums: **GREEN**
- Per-document SHA-256 and persisted JSONL checksums: **GREEN**
- Pure builder works without external refs, images, Listing or Inventory.
- PostgreSQL remains business truth; JSONL is derived reproducibility evidence.

## Observations (not performance gates)

- Products loaded: 400
- Load duration: 0.255648 s
- Document-build duration: 0.057599 s
- Artifact-write duration: 0.010046 s
- JSONL size: 153596 bytes

## Limitations and next gates

Unicode 15.0.0 tables (Python 3.12) are required for v1 builds; different tables fail explicitly rather than silently change normalization. Derived manifests contain no durations or timestamps; observational evidence is intentionally run-specific.

Runtime least-privilege database roles remain a platform task. This gate reads but does not modify the database, fixture ingestion, or Visual V1. Retrieval was not implemented: no Search schema/tables, FTS, vectors, embeddings, RRF or Commerce.

EVAL-TEXT-V1 still needs a frozen protocol/query set and human relevance judgments. ADR-ML-002 still needs an accepted PostgreSQL lexical configuration and implementation scope.
