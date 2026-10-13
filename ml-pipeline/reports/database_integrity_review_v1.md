# DB-CONTRACT-V1 Integrity Review

Status: **GREEN**  
Review version: `db-contract-v1-integrity-review`  
Database: `sahulat_ai_dev` on PostgreSQL `18.6`  
Generated (UTC): `2026-09-10T18:45:23.998Z`

## Integrity checks

- same_product_variant_image_fk: PASS
- single_unarchived_default_variant: PASS
- inventory_null_and_bounds_constraints: PASS
- draft_listing_allows_null_currency: PASS
- active_listing_commercial_state_constrained: PASS
- audit_foreign_keys_preserve_history: PASS
- only_external_lineage_refs_cascade: PASS
- external_product_identity_unique: PASS
- no_exact_duplicate_indexes: PASS
- all_prefix_overlaps_justified: PASS
- migration_checksum_matches_source: PASS
- public_has_no_table_privileges: PASS
- required_constraints_present: PASS
- required_indexes_present: PASS
- base_schema_validation_green: PASS

## Index review

- Total indexes: 45
- Constraint-backed: 22
- Explicit: 23
- Exact duplicates: 0
- Prefix candidates: 1

- `product_variants_pkey` / `uq_product_variants_id_product`: **INTENTIONAL** — Composite uniqueness is required as the target of the same-product image foreign key.

No exact duplicate index exists. The only same-predicate left-prefix overlap is
retained because PostgreSQL requires the composite unique target used by the
same-product ProductImage foreign key.

## Security boundary

The live database currently has only the `postgres` login role and PUBLIC has no
table privileges on the five application schemas. `postgres` is explicitly an
administration/migration identity, not the future application identity.

Deferred before runtime/backend deployment:

- No application login role exists. postgres is migration/local administration only; create a non-superuser runtime role before backend or worker deployment.
- PUBLIC currently has no privileges. When runtime roles are introduced, grant audit INSERT/SELECT as needed and withhold UPDATE, DELETE, and TRUNCATE.

These are role-provisioning controls, not contradictions in Migration 001. The
schema contract is frozen; changing schema semantics requires a new migration.
