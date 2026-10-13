-- Apply after backend commerce migration 005 as the schema owner. Grant this
-- NOLOGIN capability role to a dedicated non-superuser LOGIN outside this file.
BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sahulat_commerce_runtime') THEN
        CREATE ROLE sahulat_commerce_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname = 'sahulat_commerce_runtime'
          AND (rolcanlogin OR rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)
    ) THEN
        RAISE EXCEPTION 'sahulat_commerce_runtime has unsafe role attributes';
    END IF;
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO sahulat_commerce_runtime', current_database());
END $$;

GRANT USAGE ON SCHEMA iam, catalog, inventory, commerce, audit, integration TO sahulat_commerce_runtime;
GRANT USAGE, SELECT ON SEQUENCE commerce.offer_number_seq, commerce.order_number_seq TO sahulat_commerce_runtime;

GRANT SELECT (id, email, display_name, status),
      UPDATE (display_name, updated_at) ON iam.users TO sahulat_commerce_runtime;
GRANT SELECT (user_id, role, status) ON iam.user_roles TO sahulat_commerce_runtime;
GRANT SELECT (user_id, phone), UPDATE (phone, updated_at)
      ON iam.customer_profiles TO sahulat_commerce_runtime;
GRANT SELECT (id, user_id, label, recipient_name, phone, address_line1, address_line2,
              city, province, postal_code, is_default, created_at, archived_at),
      INSERT (user_id, label, recipient_name, phone, address_line1, address_line2,
              city, province, postal_code, is_default),
      UPDATE (label, recipient_name, phone, address_line1, address_line2, city, province,
              postal_code, is_default, updated_at)
      ON iam.customer_addresses TO sahulat_commerce_runtime;

GRANT SELECT (id, display_name, slug, description, allow_customer_offers, status),
      UPDATE (display_name, description, allow_customer_offers, updated_at)
      ON catalog.vendors TO sahulat_commerce_runtime;
GRANT SELECT (id, vendor_id, name, status) ON catalog.products TO sahulat_commerce_runtime;
GRANT SELECT (id, product_id, variant_code, sku, status) ON catalog.product_variants TO sahulat_commerce_runtime;
GRANT SELECT (id, variant_id, price, currency, availability, status, allow_customer_offers)
      ON catalog.listings TO sahulat_commerce_runtime;
GRANT SELECT (vendor_id, user_id, role, status) ON iam.vendor_memberships TO sahulat_commerce_runtime;
GRANT SELECT (listing_id, on_hand_quantity, reserved_quantity),
      UPDATE (on_hand_quantity, reserved_quantity, updated_at)
      ON inventory.inventory_balances TO sahulat_commerce_runtime;

GRANT SELECT ON commerce.offers TO sahulat_commerce_runtime;
GRANT INSERT (customer_user_id, vendor_id, listing_id, currency, listed_price,
              offered_price, customer_message, expires_at),
      UPDATE (status, counter_price, accepted_at, updated_at)
      ON commerce.offers TO sahulat_commerce_runtime;
GRANT SELECT ON commerce.orders TO sahulat_commerce_runtime;
GRANT INSERT (customer_user_id, vendor_id, accepted_offer_id, idempotency_key, idempotency_fingerprint, status,
              payment_method, payment_status, currency, subtotal, discount_total,
              delivery_total, total, delivery_name, delivery_phone, delivery_address_line1,
              delivery_address_line2, delivery_city, delivery_province, delivery_postal_code),
      UPDATE (status, payment_status, updated_at, cancelled_at, completed_at)
      ON commerce.orders TO sahulat_commerce_runtime;
GRANT SELECT ON commerce.order_items TO sahulat_commerce_runtime;
GRANT INSERT (order_id, listing_id, product_id, variant_id, item_name, variant_code,
              sku, unit_price, currency, quantity, discount_total, line_total)
      ON commerce.order_items TO sahulat_commerce_runtime;
GRANT SELECT ON inventory.inventory_reservations TO sahulat_commerce_runtime;
GRANT INSERT (order_item_id, listing_id, quantity),
      UPDATE (status, updated_at, released_at, consumed_at)
      ON inventory.inventory_reservations TO sahulat_commerce_runtime;
GRANT INSERT ON audit.audit_log TO sahulat_commerce_runtime;
GRANT INSERT ON integration.outbox_events TO sahulat_commerce_runtime;

COMMIT;
