\set ON_ERROR_STOP on

-- Rollback-only capability and commerce invariant smoke. Run after migration 005.
BEGIN;
SELECT uuidv7()::text AS customer_id, uuidv7()::text AS vendor_user_id,
       uuidv7()::text AS vendor_id, uuidv7()::text AS product_id,
       uuidv7()::text AS variant_id, uuidv7()::text AS listing_id \gset

INSERT INTO iam.users (id, email, email_normalized, password_hash, display_name, status, email_verified_at)
VALUES (:'customer_id'::uuid, :'customer_id' || '@example.invalid', :'customer_id' || '@example.invalid',
        '$argon2id$smoke-only', 'Commerce Customer', 'active', now()),
       (:'vendor_user_id'::uuid, :'vendor_user_id' || '@example.invalid', :'vendor_user_id' || '@example.invalid',
        '$argon2id$smoke-only', 'Commerce Vendor', 'active', now());
INSERT INTO iam.user_roles (user_id, role) VALUES (:'customer_id'::uuid, 'customer');
INSERT INTO iam.customer_profiles (user_id) VALUES (:'customer_id'::uuid);
INSERT INTO catalog.vendors (id, display_name, slug, status)
VALUES (:'vendor_id'::uuid, 'Commerce Smoke Vendor', 'commerce-smoke-' || :'vendor_id', 'active');
INSERT INTO iam.vendor_memberships (vendor_id, user_id, role, status)
VALUES (:'vendor_id'::uuid, :'vendor_user_id'::uuid, 'owner', 'active');
INSERT INTO catalog.products (id, vendor_id, name, description, status, published_at)
VALUES (:'product_id'::uuid, :'vendor_id'::uuid, 'Commerce Smoke Product', 'Rollback-only fixture', 'published', now());
INSERT INTO catalog.product_variants (id, product_id, variant_code, status, is_default)
VALUES (:'variant_id'::uuid, :'product_id'::uuid, 'default', 'active', true);
INSERT INTO catalog.listings (id, variant_id, price, currency, availability, status)
VALUES (:'listing_id'::uuid, :'variant_id'::uuid, 2000, 'PKR', 'in_stock', 'active');
INSERT INTO inventory.inventory_balances (listing_id, on_hand_quantity) VALUES (:'listing_id'::uuid, 10);

SET ROLE sahulat_commerce_runtime;
SELECT has_column_privilege(current_user, 'commerce.orders', 'customer_user_id', 'INSERT')
   AND has_column_privilege(current_user, 'commerce.orders', 'status', 'UPDATE')
   AND NOT has_column_privilege(current_user, 'commerce.orders', 'customer_user_id', 'UPDATE')
   AND NOT has_table_privilege(current_user, 'commerce.orders', 'DELETE')
   AND NOT has_table_privilege(current_user, 'commerce.payment_events', 'INSERT')
   AND NOT has_schema_privilege(current_user, 'commerce', 'CREATE') AS commerce_role_limited \gset
\if :commerce_role_limited
\else
    SELECT 1/0;
\endif

INSERT INTO commerce.offers (
    customer_user_id, vendor_id, listing_id, currency, listed_price, offered_price, expires_at
) VALUES (:'customer_id'::uuid, :'vendor_id'::uuid, :'listing_id'::uuid, 'PKR', 2000, 1800, now() + interval '7 days')
RETURNING id::text AS offer_id \gset
UPDATE commerce.offers SET status = 'accepted', accepted_at = now(), updated_at = now()
WHERE id = :'offer_id'::uuid;
INSERT INTO commerce.orders (
    customer_user_id, vendor_id, accepted_offer_id, idempotency_key, idempotency_fingerprint, status,
    payment_method, payment_status, currency, subtotal, discount_total, delivery_total, total,
    delivery_name, delivery_phone, delivery_address_line1, delivery_city
) VALUES (
    :'customer_id'::uuid, :'vendor_id'::uuid, :'offer_id'::uuid, uuidv7(), repeat('a', 64), 'placed',
    'cash_on_delivery', 'cod_due', 'PKR', 2000, 200, 0, 1800,
    'Commerce Customer', '+920000000000', 'Rollback Street', 'Karachi'
) RETURNING id::text AS order_id \gset
INSERT INTO commerce.order_items (
    order_id, listing_id, product_id, variant_id, item_name, variant_code,
    unit_price, currency, quantity, discount_total, line_total
) VALUES (
    :'order_id'::uuid, :'listing_id'::uuid, :'product_id'::uuid, :'variant_id'::uuid,
    'Commerce Smoke Product', 'default', 2000, 'PKR', 1, 200, 1800
) RETURNING id::text AS item_id \gset
UPDATE inventory.inventory_balances SET reserved_quantity = reserved_quantity + 1
WHERE listing_id = :'listing_id'::uuid;
INSERT INTO inventory.inventory_reservations (order_item_id, listing_id, quantity)
VALUES (:'item_id'::uuid, :'listing_id'::uuid, 1);
SELECT set_config('sahulat.test_order_id', :'order_id', true);
DO $$
BEGIN
    BEGIN
        UPDATE commerce.orders SET status = 'completed'
        WHERE id = current_setting('sahulat.test_order_id')::uuid;
        RAISE EXCEPTION 'invalid order transition was not rejected';
    EXCEPTION WHEN check_violation THEN
        NULL;
    END;
END $$;
INSERT INTO audit.audit_log (actor_user_id, vendor_id, entity_type, entity_id, action)
VALUES (:'customer_id'::uuid, :'vendor_id'::uuid, 'order', :'order_id'::uuid, 'order.placed');
INSERT INTO integration.outbox_events (event_type, aggregate_type, aggregate_id)
VALUES ('order.placed', 'order', :'order_id'::uuid);
RESET ROLE;

SELECT EXISTS (
    SELECT 1 FROM commerce.orders o
    JOIN commerce.order_items oi ON oi.order_id = o.id
    JOIN inventory.inventory_reservations r ON r.order_item_id = oi.id
    JOIN inventory.inventory_balances b ON b.listing_id = r.listing_id
    WHERE o.id = :'order_id'::uuid AND o.total = 1800 AND o.status = 'placed'
      AND r.status = 'active' AND b.reserved_quantity = 1
) AS commerce_write_ok \gset
\if :commerce_write_ok
\else
    SELECT 1/0;
\endif
ROLLBACK;
\echo 'Commerce capability smoke passed; fixture transaction rolled back.'
