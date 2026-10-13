# ADR-ML-004: Product text document construction

Status: **ACCEPTED after pure-builder and PostgreSQL integration verification**  
Version: `ADR-ML-004-v1`  
Date: 2026-09-12  
Authority: accepted ADR-DATA-001 / ProductVariant addendum and frozen DB-CONTRACT-V1

## Purpose and scope

Freeze the deterministic, retriever-independent transformation from committed canonical
Product semantics to `product-text-v1`. This implements, rather than changes, the locked
Product / ProductVariant / Listing / Inventory / ProductImage boundaries. No retrieval,
evaluation labels, indexing, database migration or production event consumer is included.

PostgreSQL is canonical business-data truth. JSONL is a derived evaluation/reproducibility
artifact, never authoritative business state. Semantic database changes require rebuilding
derived documents; publishing an artifact never writes back to the catalog.

## Canonical input and database boundary

The immutable, explicitly typed input is:

```python
CanonicalProductProjection(
    product_id: UUID,
    name: str,
    description: str,
    colors: tuple[str, ...],
)
```

The UUID is internal identity, not a searchable field. No sessions, ORM entities, raw forms,
fixture column names or Listing data enter the pure builder. The core API is
`build_product_document(projection) -> ProductTextDocument`; the batch API accepts an iterable
of projections, rejects duplicate canonical identities and returns documents in canonical
UUID string order. Both work without a database or fixture metadata.

The read-only PostgreSQL adapter loads `catalog.products` and `catalog.product_variants`
in one statement/snapshot. Every Product with `archived_at IS NULL` and status other than
`archived` is in scope, including `draft`, `published` and `paused`. This is **semantic document
eligibility**, not permission to serve a product as an active commercial listing. Future
published-only search eligibility remains a separate approved indexing/service policy.

Variant colors are applicable when `archived_at IS NULL` and status is not `archived`;
draft, active and paused variants participate. Null colors are omitted by the loader.
Neither Listing, Inventory, external refs, images nor a default-variant join is required to
render semantics. The application still owns the frozen at-least-one-default-variant invariant.
Migration provenance is read separately in the same statement from `integration.schema_migrations`.

Archived Product IDs are reported as exclusions. In-scope inputs with missing/non-UUID/nil
identity, non-string or normalized-empty Name/Description, or invalid Unicode fail explicitly
and abort the batch **before publishing any artifact**. There is no silent repair, fallback
or invented description. Color is optional; empty normalized colors are omitted.

## Included and excluded fields

Included fields and ordering are immutable: **Name -> Description -> optional Color**.

Excluded from both text and machine semantic fields: Price, Currency, Availability, Stock,
Size, Brand, Category, Vendor, product ID, SKU, listing ID/state, external IDs, image metadata,
tags, generated summaries/keywords, inferred attributes and retrieval-specific tokens/scores.
`product_id` exists only as machine identity metadata. Source Name/Description are not redacted
if their original prose happens to mention a price, brand, size or other concept; exclusion
means those separate structured fields are never appended to the document.

## Normalization policy

`product-normalization-v1` uses the **shared existing Gate 1/ingestion policy**:

1. Unicode NFKC normalization.
2. Replace each Unicode category `Cc` control character with one ASCII space. This removes
   controls without joining adjacent words, exactly matching the audited policy.
3. Trim outer Unicode whitespace.
4. Collapse each `\s+` run to one ASCII space.
5. Preserve meaningful punctuation, original script/language and case.

Format characters (`Cf`, including meaningful script joiners) are not indiscriminately removed.
Unpaired surrogates cannot enter strict UTF-8 serialization and fail explicitly. There is no
translation, transliteration, spelling correction, stemming, synonym expansion, lowercasing,
stop-word removal, summarization, LLM rewriting, keyword generation or attribute inference.

To prevent normalization drift across Python Unicode table releases, document builds require
Unicode **15.0.0** (the current Python 3.12 runtime). Other Unicode tables fail explicitly.
The broader package's supported Python range is unchanged. Changing this document policy or
its Unicode tables requires a new document schema version, not silently redefining v1.

## Multi-variant Color semantics

Normalize every supplied variant color; remove normalized-empty values; deduplicate exact
normalized strings; sort by Unicode code-point order, case-sensitive and locale-independent.
Database/insertion order has no meaning. Do not split compound free-text colors or create an
ontology. Render the ordered list with **`, `** (comma plus ASCII space).

`Blue`, `black`, `Blue`, `  Red`, null becomes `Blue`, `Red`, `black`.
`Blue` and `blue` remain distinct. A single/default Khaadi variant gives the same optional Color
semantics as the source; multiple future vendor variants use this identical builder.

## Canonical text rendering

```text
Product Name: <normalized name>
Description: <normalized description>
Color: <ordered colors joined with comma and space>
```

Labels, colon plus ASCII space and field order are fixed. Lines are separated by one LF (`\n`).
There is **no trailing newline inside `text`**. With no usable colors, omit the entire Color
line; never insert `N/A`, `Unknown`, null or other placeholders into searchable text.

## Machine serialization and checksums

Each JSONL record contains exactly:

```json
{
  "schema_version": "product-text-v1",
  "product_id": "<lowercase hyphenated canonical UUID>",
  "fields": {"name": "...", "description": "...", "colors": ["..."]},
  "text": "Product Name: ...\nDescription: ...\nColor: ...",
  "document_checksum": "sha256:<lowercase hex>"
}
```

Missing Color produces `colors: []`. Object order in the displayed example is explanatory;
canonical serialization sorts object keys recursively. Python JSON settings are
`sort_keys=True`, `separators=(',', ':')`, `ensure_ascii=False`, `allow_nan=False`.
Encoding is strict UTF-8 without BOM. There is no trailing newline in checksum input.

The per-document checksum is SHA-256 of this exact canonical record **excluding only
`document_checksum`**: schema version, canonical Product UUID, normalized fields and rendered
text all participate. Timestamps, paths, connection information, run IDs, row ordering,
external identities and session/query metadata never participate. Identity changes therefore
change document checksums; unchanged internal fixture UUIDs are supplied by ingestion.

Artifact policy: sort records by their lowercase hyphenated UUID strings in ascending Unicode
code-point order, serialize each complete record as above, append one LF to **every** record,
including the final one, concatenate bytes and SHA-256 the entire JSONL. An empty batch is
zero bytes. Artifact checksums also use `sha256:<lowercase hex>`.

Same committed canonical semantics, identities, schema policy and Unicode tables produce
identical records, document checksums and JSONL bytes across machines. Concurrent semantic
edits between the two verification loads fail the gate rather than publishing mixed evidence.

## Artifacts, provenance and operation

- `artifacts/product_documents/product-text-v1.jsonl`: deterministic derived documents.
- `product-text-v1.manifest.json`: schema, normalization/Unicode versions, ADR status/version,
  DB contract, verified migration checksum/history, builder version, sort policy, counts,
  excluded IDs, per-document checksums, artifact checksum and optional verified fixture lineage.
- `product-text-v1-build.json`: machine verification evidence and observational durations.
- `reports/product_text_v1_build.md`: report reproduced from that evidence.

The manifest checksum hashes its canonical object excluding `manifest_checksum`. Canonical
manifest and JSONL contain no timestamps or performance measurements. Build evidence/report
durations are intentionally observational and run-specific, never semantic checksum inputs.
Each file is atomically replaced after validation; its checksums detect incomplete/mixed
publication. There is no claim of an atomic multi-file transaction.

`python scripts/build_product_text_v1.py` uses existing environment configuration. Optional
`--verify-khaadi-lineage` validates the frozen fixture source and existing ingestion parity
before recording its semantic checksum as provenance. This CLI-only verification is not a
dependency of the Product projection loader or builder; arbitrary canonical vendor Products
do not need external refs or Khaadi artifacts. No secrets or absolute machine paths are emitted.

## Rebuild and future indexing contract

Rebuild after Name/Description changes, relevant variant Color addition/change/removal,
variant archive/restore changing the normalized color set, or Product archive/restore changing
semantic eligibility. Future index entries for removed/archived Products need tombstoning.
Compare semantic checksums: changes that normalize to the same document do not require re-embedding.

Do **not** rebuild for Price, Currency, Availability, Stock, listing state, images/image embeddings,
Size, Brand, Category, offers or orders. A later explicitly accepted commercial search-eligibility
policy may change which documents are served without redefining their semantic text.
No Outbox consumer, domain event trigger or indexing implementation is created here.

Future PostgreSQL FTS and dense retrievers consume the same canonical representation. Adding
fields, changing labels/separators/order, normalization or color semantics requires
`product-text-v2`, fresh artifacts and later version-compatible indexes/embeddings. Never overwrite
the meaning of `product-text-v1`.

## Rejected alternatives and consequences

- Building around Khaadi CSV columns: creates a fixture-specific production contract.
- Appending volatile commerce fields: forces unnecessary document rebuilds/re-embedding.
- Color ontology/inference or model-specific formatting: alters source meaning or couples retrievers.
- Row-order color rendering, locale sorting or nondeterministic JSON: breaks reproducibility.
- Placeholder required fields: conceals malformed canonical data.
- JSONL as business truth: reverses PostgreSQL source-of-truth ownership.
- ORM/session-aware rendering: prevents pure, portable construction and lightweight tests.
- Silently accepting different Unicode tables: allows v1 normalization drift.

The existing 400 canonical fixture Products may all yield documents only when live eligibility
and field validation prove that count. Builder logic never hardcodes fixture population size.
The fixture's absent Currency, Size, Brand, Category and Stock stay absent; neither ingestion
nor Visual V1 changes. EVAL-TEXT-V1 and ADR-ML-002 remain separate, unimplemented gates.
