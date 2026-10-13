-- Apply after catalog-core migration 001 as the schema owner. Grant this
-- NOLOGIN capability role to a dedicated non-superuser LOGIN outside this file.
BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sahulat_catalog_writer') THEN
        CREATE ROLE sahulat_catalog_writer NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_roles
        WHERE rolname = 'sahulat_catalog_writer'
          AND (rolcanlogin OR rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)
    ) THEN
        RAISE EXCEPTION 'sahulat_catalog_writer has unsafe role attributes';
    END IF;

    EXECUTE format('GRANT CONNECT ON DATABASE %I TO sahulat_catalog_writer', current_database());
END $$;

GRANT USAGE ON SCHEMA iam, catalog, inventory TO sahulat_catalog_writer;
GRANT SELECT (id, status) ON iam.users TO sahulat_catalog_writer;
GRANT SELECT (vendor_id, user_id, status, role) ON iam.vendor_memberships TO sahulat_catalog_writer;
GRANT SELECT (id, status) ON catalog.vendors TO sahulat_catalog_writer;
GRANT INSERT (vendor_id, name, description, status, created_by_user_id, updated_by_user_id),
      UPDATE (name, description, category_id, status, published_at, updated_by_user_id, updated_at),
      SELECT (id, vendor_id, category_id, name, status, archived_at) ON catalog.products TO sahulat_catalog_writer;
GRANT SELECT (id, status) ON catalog.categories TO sahulat_catalog_writer;
GRANT INSERT (product_id, variant_code, status, is_default),
      UPDATE (variant_code, sku, color, size, updated_at),
      SELECT (id, product_id, status, is_default, archived_at) ON catalog.product_variants TO sahulat_catalog_writer;
GRANT INSERT (variant_id, price, currency, availability, allow_customer_offers, status),
      UPDATE (status, price, currency, availability, allow_customer_offers, updated_at),
      SELECT (id, variant_id, price, currency, availability, allow_customer_offers, status, archived_at) ON catalog.listings TO sahulat_catalog_writer;
GRANT INSERT (product_id, storage_key, mime_type, width, height, sha256, status, is_primary),
      SELECT (id, product_id, variant_id, status, is_primary, archived_at)
      ON catalog.product_images TO sahulat_catalog_writer;
GRANT INSERT (listing_id, on_hand_quantity),
      UPDATE (on_hand_quantity, updated_at),
      SELECT (listing_id, on_hand_quantity, reserved_quantity)
      ON inventory.inventory_balances TO sahulat_catalog_writer;

COMMIT;
