# Sahulat AI Database Contract V1

Status: **FROZEN after DB integrity review**  
Migration: `20260910_001_catalog_core_v1`  
Authority: ADR-DATA-001 and its accepted ProductVariant addendum

## Scope and ownership

PostgreSQL is the business-data source of truth. The versioned migration under
`database/migrations/` is the current schema source of truth. The repository has no ASP.NET
Core infrastructure project yet, so Migration 001 uses a minimal, checksum-verified SQL
migration boundary rather than inventing a backend. When the backend exists, one designated
backend/infrastructure owner must establish an EF Core baseline from this migration and own all
subsequent migrations; SQL and EF migration chains must not evolve in parallel.

Only these domain schemas exist:

| Schema | Responsibility |
| --- | --- |
| `iam` | Users and vendor membership |
| `catalog` | Vendors, product identity, variants, listings, images, external references |
| `inventory` | Mutable stock balances |
| `integration` | Migration history and transactional outbox |
| `audit` | Append-only audit records |

The canonical commercial ownership chain is:

```text
Vendor -> Product -> ProductVariant -> Listing -> InventoryBalance
                    |
                    +-> ProductImage (optional variant association)
```

Product owns stable semantics. ProductVariant owns Color and Size. Listing owns Price,
Currency, Availability, and listing lifecycle. InventoryBalance owns quantities. ProductImage
always belongs to Product and may additionally belong to a variant of that same Product.

## Entities

### IAM

`iam.users` stores normalized unique email identity and Argon2id encoded password hashes.
Statuses are `pending`, `active`, `suspended`, and `archived`. Verification, login, and archive
timestamps remain nullable until those lifecycle events occur. Password and refresh-token flows
are not implemented.

`iam.vendor_memberships` is the many-to-many tenancy boundary. A `(vendor_id, user_id)` pair is
unique. Roles are `owner`, `manager`, `staff`, and `viewer`; statuses are `pending`, `active`,
`suspended`, and `revoked`. Vendor ownership is never stored directly on `iam.users`.

`iam.refresh_sessions` is deliberately deferred. Rotation, reuse detection, session-family
revocation, and expiry ownership are not yet locked; creating the table now would invent
unfinished authentication behavior. Raw refresh tokens must never be stored when this contract
is later defined.

### Catalog

`catalog.vendors` owns the tenant business identity. Slugs are globally unique and normalized by
constraint. Statuses are `pending`, `active`, `suspended`, and `archived`.

`catalog.categories` is a self-referencing hierarchy with globally unique slugs and deterministic
non-negative `sort_order`. No category taxonomy is seeded by Migration 001.

`catalog.products` contains required Name and Description plus optional vendor-supplied Brand and
Category. Statuses are `draft`, `published`, `paused`, and `archived`; a published row requires
`published_at`. It intentionally has no price, currency, availability, stock, search vector, or
embedding.

`catalog.product_variants` contains required `variant_code`, optional SKU, optional Color,
optional Size, lifecycle status, and `is_default`. A partial unique index prevents more than one
unarchived default variant per product. Another partial unique index prevents reuse of an
unarchived variant code within a product. At least one default variant is a transaction-level
application invariant because a row-local constraint cannot enforce existence without a
cross-row trigger; Migration 001 intentionally adds no domain triggers.

`catalog.listings` stores `NUMERIC(12,2)` Price, optional three-letter uppercase Currency,
Availability, and lifecycle state. Availability is one of `unknown`, `in_stock`, `out_of_stock`,
`preorder`, or `unavailable`; status is `draft`, `active`, `paused`, or `archived`. Draft and
incomplete fixture records may have null Price/Currency. Active listings require non-null Price
and Currency and non-`unknown` Availability. Any supplied Price must be non-negative.

`catalog.product_images` stores metadata and a canonical `storage_key`, never image bytes. Width
and height must be positive when known; SHA-256 must be lowercase hexadecimal when known. The
composite foreign key `(variant_id, product_id)` proves that an optional variant belongs to the
same product. Partial unique indexes allow one unarchived primary product-level image and one
unarchived primary image per variant.

`catalog.product_external_refs` and `catalog.image_external_refs` map external dataset identities
to canonical UUIDs. Source-system identities are unique. External image paths must be portable
relative paths; drive-qualified, root-qualified, and UNC-style paths are rejected.

### Inventory

`inventory.inventory_balances` has one row per Listing. `on_hand_quantity IS NULL` means unknown
or not supplied; `0` means confirmed zero. Reserved quantity is non-negative and cannot exceed a
known on-hand quantity. Warehouse and location modeling is outside V1.

### Integration

`integration.schema_migrations` provides the minimal migration ownership boundary. Each migration
ID is recorded once with its SHA-256 file checksum and PostgreSQL version. Reapplication with the
same checksum is a no-op; checksum drift fails safely. An advisory transaction lock serializes
migration application.

`integration.outbox_events` is the application-owned transactional outbox foundation. Payloads
are JSON objects. Statuses are `pending`, `processing`, `processed`, and `failed`; attempt count is
non-negative. A partial index supports ordered pending-event polling. Migration 001 creates no
event triggers and no consumer.

### Audit

`audit.audit_log` stores optional actor/vendor references, entity identity, action, request ID, and
optional JSON object snapshots. User/vendor deletion uses `SET NULL`, preserving audit history.
Append-only behavior is an application/permission intent until database roles are designed; no
automatic audit trigger is created.

The current local `postgres` login is an administration/migration identity only. It is not the
future backend or ML-worker application account. Before runtime deployment, provision dedicated
non-superuser roles and withhold `UPDATE`, `DELETE`, and `TRUNCATE` on `audit.audit_log` from normal
application roles. Migration 001 grants no table privileges to PUBLIC.

## Identifier and timestamp policy

Canonical entities use PostgreSQL 18 `uuidv7()` defaults. Lifecycle timestamps use `timestamptz`
with UTC operational semantics. `created_at` has a database `now()` default. `updated_at` also has
an insert default, but application code owns all later updates; there is no misleading automatic
update trigger.

Physical names use unquoted `snake_case`, plural table names, singular column names, and
`<entity>_id` foreign keys.

## Delete behavior

Physical deletion is exceptional; long-lived entities should be archived.

| Relationship | `ON DELETE` | Reason |
| --- | --- | --- |
| Vendor/Product/Variant/Listing ownership | `RESTRICT` | Prevent accidental business-data erasure |
| Vendor membership to User/Vendor | `RESTRICT` | Require explicit membership handling |
| Category parent | `RESTRICT` | Prevent implicit subtree mutation |
| Product to Category | `SET NULL` | Category removal does not remove Product |
| Created/updated user references | `SET NULL` | Preserve the business row |
| ProductImage to Product/Variant | `RESTRICT` | Preserve ownership integrity |
| External refs to Product/Image | `CASCADE` | References have no identity without their physically removed owner |
| Audit actor/vendor | `SET NULL` | Audit history must survive principal removal |

No blanket cascade policy is used.

## Indexing policy

Primary-key and ordinary unique constraints create PostgreSQL B-tree indexes automatically.
Migration 001 adds only foreign-key join, lifecycle lookup, integrity, and pending-outbox indexes:

- vendor creator; membership user; category parent
- Product `(vendor_id, status)`, category, creator, and updater
- Variant product lookup, unarchived code uniqueness, and unarchived default uniqueness
- Listing variant, `(status, availability)`, and `(currency, price)`
- Image product/sort, variant, and scoped primary-image uniqueness
- External-reference owner lookups
- pending Outbox `(occurred_at, id)`
- Audit actor, vendor/time, and entity/time lookups

No FTS, GIN text-search, vector, ANN, analytics, or speculative query index exists.

## Khaadi mapping (documentation only)

Migration 001 imports no fixture data. A future importer will create one default variant per valid
fixture Product.

| Khaadi field | Canonical destination |
| --- | --- |
| ID | `catalog.product_external_refs.external_product_id` |
| Product Name | `catalog.products.name` |
| Product Description | `catalog.products.description` |
| Color | `catalog.product_variants.color` |
| Price | `catalog.listings.price` |
| Availability | `catalog.listings.availability` after an approved deterministic mapping |
| Size | `NULL` / unsupported |
| Currency | `NULL` / unsupported unless the source proves otherwise |
| Brand | `NULL` / unsupported |
| Category | `NULL` / unsupported |

External Khaadi IDs never become production primary keys. Currency, Size, Brand, and Category are
not inferred.

## Derived and future boundaries

Khaadi CSV is an evaluation fixture. JSONL is a reproducibility artifact. Search documents,
embeddings, and analytics are derived data. `search`, `commerce`, and `analytics` schemas are not
part of Migration 001. Search documents wait for ADR-ML-004; FTS waits for ADR-ML-002; vectors
wait for an encoder/dimension decision; Commerce waits for its workflow contract.

Apply and verify locally with verified `.env` credentials:

```powershell
python scripts/apply_database_migrations.py
python scripts/verify_database_schema.py
python scripts/review_database_integrity.py
$env:RUN_DATABASE_TESTS = "1"
pytest tests/database/test_catalog_core_schema.py
```
