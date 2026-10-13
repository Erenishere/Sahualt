# Database Schema Validation V1

- Status: **GREEN**
- Database: `sahulat_ai_dev`
- PostgreSQL: `18.6`
- Migration: `20260910_001_catalog_core_v1`
- Generated (UTC): `2026-09-10T18:45:21.412Z`

## Catalog checks

- expected_schemas_only: PASS
- expected_tables_only: PASS
- migration_recorded_once: PASS
- uuidv7_available: PASS
- forbidden_schemas_absent: PASS
- forbidden_tables_absent: PASS
- tsvector_absent: PASS
- pgvector_absent: PASS

## Counts

- Schemas: 5
- Tables: 14
- Primary keys: 14
- Foreign keys: 17
- Unique constraints: 8
- Check constraints: 61
- Indexes (including constraint indexes): 45

## Tables

- `audit.audit_log`
- `catalog.categories`
- `catalog.image_external_refs`
- `catalog.listings`
- `catalog.product_external_refs`
- `catalog.product_images`
- `catalog.product_variants`
- `catalog.products`
- `catalog.vendors`
- `iam.users`
- `iam.vendor_memberships`
- `integration.outbox_events`
- `integration.schema_migrations`
- `inventory.inventory_balances`

## Indexes

- `audit.audit_log_pkey` on `audit_log`
- `audit.ix_audit_log_actor_user_id` on `audit_log`
- `audit.ix_audit_log_entity` on `audit_log`
- `audit.ix_audit_log_vendor_id_created_at` on `audit_log`
- `catalog.categories_pkey` on `categories`
- `catalog.ix_categories_parent_id` on `categories`
- `catalog.uq_categories_slug` on `categories`
- `catalog.image_external_refs_pkey` on `image_external_refs`
- `catalog.ix_image_external_refs_image_id` on `image_external_refs`
- `catalog.uq_image_external_refs_source_external` on `image_external_refs`
- `catalog.ix_listings_currency_price` on `listings`
- `catalog.ix_listings_status_availability` on `listings`
- `catalog.ix_listings_variant_id` on `listings`
- `catalog.listings_pkey` on `listings`
- `catalog.ix_product_external_refs_product_id` on `product_external_refs`
- `catalog.product_external_refs_pkey` on `product_external_refs`
- `catalog.uq_product_external_refs_source_external` on `product_external_refs`
- `catalog.ix_product_images_product_sort_order` on `product_images`
- `catalog.ix_product_images_variant_id` on `product_images`
- `catalog.product_images_pkey` on `product_images`
- `catalog.uq_product_images_primary_product` on `product_images`
- `catalog.uq_product_images_primary_variant` on `product_images`
- `catalog.uq_product_images_storage_key` on `product_images`
- `catalog.ix_product_variants_product_id` on `product_variants`
- `catalog.product_variants_pkey` on `product_variants`
- `catalog.uq_product_variants_default_active` on `product_variants`
- `catalog.uq_product_variants_id_product` on `product_variants`
- `catalog.uq_product_variants_product_variant_code_active` on `product_variants`
- `catalog.ix_products_category_id` on `products`
- `catalog.ix_products_created_by_user_id` on `products`
- `catalog.ix_products_updated_by_user_id` on `products`
- `catalog.ix_products_vendor_status` on `products`
- `catalog.products_pkey` on `products`
- `catalog.ix_vendors_created_by_user_id` on `vendors`
- `catalog.uq_vendors_slug` on `vendors`
- `catalog.vendors_pkey` on `vendors`
- `iam.uq_users_email_normalized` on `users`
- `iam.users_pkey` on `users`
- `iam.ix_vendor_memberships_user_id` on `vendor_memberships`
- `iam.uq_vendor_memberships_vendor_user` on `vendor_memberships`
- `iam.vendor_memberships_pkey` on `vendor_memberships`
- `integration.ix_outbox_events_pending` on `outbox_events`
- `integration.outbox_events_pkey` on `outbox_events`
- `integration.schema_migrations_pkey` on `schema_migrations`
- `inventory.inventory_balances_pkey` on `inventory_balances`

The JSON companion contains every column, data type, nullability rule, default,
constraint definition, foreign-key delete action, index definition, migration
checksum, row count, and forbidden-infrastructure check used by this report.
