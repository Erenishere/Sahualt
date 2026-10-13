-- Apply after backend commerce migration 005, as the database schema owner.
-- This grants a NOLOGIN capability role only. Provision a separate non-superuser
-- LOGIN and grant it membership in sahulat_assistant_reader outside this file.
BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sahulat_assistant_reader') THEN
        CREATE ROLE sahulat_assistant_reader NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_roles
        WHERE rolname = 'sahulat_assistant_reader'
          AND (rolcanlogin OR rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)
    ) THEN
        RAISE EXCEPTION 'sahulat_assistant_reader has unsafe role attributes';
    END IF;

    EXECUTE format('GRANT CONNECT ON DATABASE %I TO sahulat_assistant_reader', current_database());
END $$;

GRANT USAGE ON SCHEMA iam, catalog, inventory TO sahulat_assistant_reader;

GRANT SELECT (id, status) ON iam.users TO sahulat_assistant_reader;
GRANT SELECT (user_id, role, status) ON iam.user_roles TO sahulat_assistant_reader;
GRANT SELECT (vendor_id, user_id, status, role) ON iam.vendor_memberships TO sahulat_assistant_reader;
GRANT SELECT (id, display_name, slug, description, allow_customer_offers, status) ON catalog.vendors TO sahulat_assistant_reader;
GRANT SELECT (id, vendor_id, category_id, name, description, status, published_at, archived_at) ON catalog.products TO sahulat_assistant_reader;
GRANT SELECT (id, parent_id, name, status, sort_order) ON catalog.categories TO sahulat_assistant_reader;
GRANT SELECT (id, product_id, variant_code, sku, color, size, status, is_default) ON catalog.product_variants TO sahulat_assistant_reader;
GRANT SELECT (id, variant_id, status, price, currency, availability, allow_customer_offers) ON catalog.listings TO sahulat_assistant_reader;
GRANT SELECT (id, product_id, storage_key, mime_type, width, height, is_primary, sort_order, status, archived_at)
    ON catalog.product_images TO sahulat_assistant_reader;
GRANT SELECT (listing_id, on_hand_quantity, reserved_quantity) ON inventory.inventory_balances TO sahulat_assistant_reader;

COMMIT;
