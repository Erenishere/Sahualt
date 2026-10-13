\set ON_ERROR_STOP on

-- Run only on a development database after migration 001 and the
-- capability-role scripts. Every fixture and draft is rolled back.
BEGIN;

SELECT uuidv7()::text AS editor_id, uuidv7()::text AS owner_id,
       uuidv7()::text AS viewer_id,
       uuidv7()::text AS vendor_id, uuidv7()::text AS other_vendor_id,
       uuidv7()::text AS category_id \gset

INSERT INTO iam.users (id, email, email_normalized, password_hash, display_name, status)
VALUES (:'editor_id'::uuid, :'editor_id' || '@example.invalid', :'editor_id' || '@example.invalid', '$argon2id$test-fixture', 'Catalog test editor', 'active'),
       (:'owner_id'::uuid, :'owner_id' || '@example.invalid', :'owner_id' || '@example.invalid', '$argon2id$test-fixture', 'Catalog test owner', 'active'),
       (:'viewer_id'::uuid, :'viewer_id' || '@example.invalid', :'viewer_id' || '@example.invalid', '$argon2id$test-fixture', 'Catalog test viewer', 'active');
INSERT INTO catalog.vendors (id, display_name, slug, status)
VALUES (:'vendor_id'::uuid, 'Catalog test vendor', 'catalog-test-' || :'vendor_id', 'active'),
       (:'other_vendor_id'::uuid, 'Other test vendor', 'catalog-test-' || :'other_vendor_id', 'active');
INSERT INTO iam.vendor_memberships (vendor_id, user_id, role, status)
VALUES (:'vendor_id'::uuid, :'editor_id'::uuid, 'staff', 'active'),
       (:'vendor_id'::uuid, :'owner_id'::uuid, 'owner', 'active'),
       (:'vendor_id'::uuid, :'viewer_id'::uuid, 'viewer', 'active');
INSERT INTO catalog.categories (id, name, slug, status)
VALUES (:'category_id'::uuid, 'Catalog test category', 'catalog-test-' || :'category_id', 'active');

SET ROLE sahulat_catalog_writer;
SELECT has_column_privilege(current_user, 'catalog.products', 'name', 'UPDATE')
   AND has_column_privilege(current_user, 'catalog.products', 'description', 'UPDATE')
   AND has_column_privilege(current_user, 'catalog.products', 'category_id', 'UPDATE')
   AND NOT has_table_privilege(current_user, 'catalog.products', 'DELETE')
   AND NOT has_schema_privilege(current_user, 'catalog', 'CREATE') AS writer_is_limited \gset
\if :writer_is_limited
\else
    \echo 'Catalog writer has broader privileges than expected'
    SELECT 1/0;
\endif
WITH created AS (
    INSERT INTO catalog.products (vendor_id, name, description, status, created_by_user_id, updated_by_user_id)
    SELECT :'vendor_id'::uuid, 'Test draft', 'Database-backed draft test', 'draft', u.id, u.id
    FROM iam.users u
    JOIN iam.vendor_memberships m ON m.user_id = u.id
    JOIN catalog.vendors v ON v.id = m.vendor_id
    WHERE u.id = :'editor_id'::uuid AND m.vendor_id = :'vendor_id'::uuid
      AND u.status = 'active' AND m.status = 'active' AND v.status = 'active'
      AND m.role IN ('owner', 'manager', 'staff')
    RETURNING id, name, status
)
SELECT id::text AS product_id, status AS created_status FROM created \gset
\if :{?product_id}
\else
    \echo 'Editor draft creation failed'
    SELECT 1/0;
\endif

UPDATE catalog.products p
SET category_id = :'category_id'::uuid, updated_by_user_id = :'editor_id'::uuid,
    updated_at = now()
WHERE p.id = :'product_id'::uuid AND p.vendor_id = :'vendor_id'::uuid
  AND p.status = 'draft'
  AND EXISTS (
      SELECT 1 FROM catalog.categories c
      WHERE c.id = :'category_id'::uuid AND c.status = 'active'
  )
  AND EXISTS (
      SELECT 1 FROM iam.users u
      JOIN iam.vendor_memberships m ON m.user_id = u.id
      JOIN catalog.vendors v ON v.id = m.vendor_id
      WHERE u.id = :'editor_id'::uuid AND m.vendor_id = :'vendor_id'::uuid
        AND u.status = 'active' AND m.status = 'active' AND v.status = 'active'
        AND m.role IN ('owner', 'manager', 'staff')
  );
SELECT category_id = :'category_id'::uuid AS category_set_ok
FROM catalog.products WHERE id = :'product_id'::uuid \gset
\if :category_set_ok
\else
    \echo 'Editor category assignment failed'
    SELECT 1/0;
\endif

WITH variant AS (
    INSERT INTO catalog.product_variants (product_id, variant_code, status, is_default)
    SELECT p.id, 'black-medium', 'active',
           NOT EXISTS (
               SELECT 1 FROM catalog.product_variants existing
               WHERE existing.product_id = p.id AND existing.is_default
                 AND existing.archived_at IS NULL
           )
    FROM catalog.products p
    JOIN catalog.vendors v ON v.id = p.vendor_id
    JOIN iam.vendor_memberships m ON m.vendor_id = v.id
    JOIN iam.users u ON u.id = m.user_id
    WHERE p.id = :'product_id'::uuid AND p.vendor_id = :'vendor_id'::uuid
      AND p.status = 'draft' AND u.id = :'editor_id'::uuid AND u.status = 'active'
      AND m.status = 'active' AND m.role IN ('owner', 'manager', 'staff')
      AND v.status = 'active'
    RETURNING id
), listing AS (
    INSERT INTO catalog.listings (variant_id, price, currency, availability, status)
    SELECT variant.id, 1999.00, 'PKR', 'in_stock', 'draft' FROM variant
    RETURNING id, variant_id
)
SELECT variant_id::text AS variant_id, id::text AS listing_id FROM listing \gset
\if :{?listing_id}
\else
    \echo 'Editor variant/listing creation failed'
    SELECT 1/0;
\endif

INSERT INTO inventory.inventory_balances (listing_id, on_hand_quantity)
VALUES (:'listing_id'::uuid, 5)
ON CONFLICT (listing_id) DO UPDATE
SET on_hand_quantity = EXCLUDED.on_hand_quantity, updated_at = now()
WHERE inventory.inventory_balances.reserved_quantity <= EXCLUDED.on_hand_quantity;

WITH created AS (
    INSERT INTO catalog.product_images (
        product_id, storage_key, mime_type, width, height, sha256, status, is_primary
    )
    SELECT p.id, 'catalog-smoke/' || :'product_id', 'image/png', 320, 240,
           repeat('a', 64), 'active',
           NOT EXISTS (
               SELECT 1 FROM catalog.product_images existing
               WHERE existing.product_id = p.id AND existing.is_primary
                 AND existing.variant_id IS NULL AND existing.archived_at IS NULL
           )
    FROM catalog.products p
    JOIN catalog.vendors v ON v.id = p.vendor_id
    JOIN iam.vendor_memberships m ON m.vendor_id = v.id
    JOIN iam.users u ON u.id = m.user_id
    WHERE p.id = :'product_id'::uuid AND p.vendor_id = :'vendor_id'::uuid
      AND p.status = 'draft' AND u.id = :'editor_id'::uuid AND u.status = 'active'
      AND m.status = 'active' AND m.role IN ('owner', 'manager', 'staff')
      AND v.status = 'active'
    RETURNING id
)
SELECT id::text AS image_id FROM created \gset
\if :{?image_id}
\else
    \echo 'Editor image metadata creation failed'
    SELECT 1/0;
\endif

WITH denied AS (
    INSERT INTO catalog.products (vendor_id, name, description, status, created_by_user_id, updated_by_user_id)
    SELECT :'vendor_id'::uuid, 'Denied viewer draft', 'Must not exist', 'draft', u.id, u.id
    FROM iam.users u
    JOIN iam.vendor_memberships m ON m.user_id = u.id
    JOIN catalog.vendors v ON v.id = m.vendor_id
    WHERE u.id = :'viewer_id'::uuid AND m.vendor_id = :'vendor_id'::uuid
      AND u.status = 'active' AND m.status = 'active' AND v.status = 'active'
      AND m.role IN ('owner', 'manager', 'staff')
    RETURNING id
)
SELECT count(*) = 0 AS viewer_denied FROM denied \gset
\if :viewer_denied
\else
    \echo 'Viewer draft creation was not denied'
    SELECT 1/0;
\endif

WITH denied AS (
    INSERT INTO catalog.products (vendor_id, name, description, status, created_by_user_id, updated_by_user_id)
    SELECT :'other_vendor_id'::uuid, 'Denied cross-vendor draft', 'Must not exist', 'draft', u.id, u.id
    FROM iam.users u
    JOIN iam.vendor_memberships m ON m.user_id = u.id
    JOIN catalog.vendors v ON v.id = m.vendor_id
    WHERE u.id = :'editor_id'::uuid AND m.vendor_id = :'other_vendor_id'::uuid
      AND u.status = 'active' AND m.status = 'active' AND v.status = 'active'
      AND m.role IN ('owner', 'manager', 'staff')
    RETURNING id
)
SELECT count(*) = 0 AS cross_vendor_denied FROM denied \gset
\if :cross_vendor_denied
\else
    \echo 'Cross-vendor draft creation was not denied'
    SELECT 1/0;
\endif

WITH denied AS (
    INSERT INTO catalog.product_variants (product_id, variant_code, status, is_default)
    SELECT p.id, 'viewer-denied', 'active', false
    FROM catalog.products p
    JOIN catalog.vendors v ON v.id = p.vendor_id
    JOIN iam.vendor_memberships m ON m.vendor_id = v.id
    JOIN iam.users u ON u.id = m.user_id
    WHERE p.id = :'product_id'::uuid AND p.vendor_id = :'vendor_id'::uuid
      AND p.status = 'draft' AND u.id = :'viewer_id'::uuid AND u.status = 'active'
      AND m.status = 'active' AND m.role IN ('owner', 'manager', 'staff')
      AND v.status = 'active'
    RETURNING id
)
SELECT count(*) = 0 AS variant_viewer_denied FROM denied \gset
\if :variant_viewer_denied
\else
    \echo 'Viewer variant creation was not denied'
    SELECT 1/0;
\endif

WITH denied AS (
    INSERT INTO catalog.product_variants (product_id, variant_code, status, is_default)
    SELECT p.id, 'cross-vendor-denied', 'active', false
    FROM catalog.products p
    JOIN catalog.vendors v ON v.id = p.vendor_id
    JOIN iam.vendor_memberships m ON m.vendor_id = v.id
    JOIN iam.users u ON u.id = m.user_id
    WHERE p.id = :'product_id'::uuid AND p.vendor_id = :'other_vendor_id'::uuid
      AND p.status = 'draft' AND u.id = :'editor_id'::uuid AND u.status = 'active'
      AND m.status = 'active' AND m.role IN ('owner', 'manager', 'staff')
      AND v.status = 'active'
    RETURNING id
)
SELECT count(*) = 0 AS variant_cross_vendor_denied FROM denied \gset
\if :variant_cross_vendor_denied
\else
    \echo 'Cross-vendor variant creation was not denied'
    SELECT 1/0;
\endif

SELECT has_column_privilege(current_user, 'catalog.product_variants', 'variant_code', 'UPDATE')
   AND has_column_privilege(current_user, 'catalog.listings', 'price', 'UPDATE')
   AND has_column_privilege(current_user, 'catalog.listings', 'allow_customer_offers', 'UPDATE')
   AND NOT has_table_privilege(current_user, 'catalog.listings', 'DELETE')
   AND NOT has_table_privilege(current_user, 'catalog.product_images', 'UPDATE')
   AS variant_writer_is_limited \gset
\if :variant_writer_is_limited
\else
    \echo 'Variant writer has broader privileges than expected'
    SELECT 1/0;
\endif

WITH published AS (
    UPDATE catalog.products p
    SET status = 'published', published_at = now(),
        updated_by_user_id = :'owner_id'::uuid, updated_at = now()
    WHERE p.id = :'product_id'::uuid AND p.vendor_id = :'vendor_id'::uuid
      AND p.status = 'draft'
      AND EXISTS (
          SELECT 1 FROM iam.users u
          JOIN iam.vendor_memberships m ON m.user_id = u.id
          JOIN catalog.vendors v ON v.id = m.vendor_id
          WHERE u.id = :'owner_id'::uuid AND m.vendor_id = :'vendor_id'::uuid
            AND u.status = 'active' AND m.status = 'active' AND v.status = 'active'
            AND m.role IN ('owner', 'manager')
      )
      AND EXISTS (
          SELECT 1 FROM catalog.categories c
          WHERE c.id = p.category_id AND c.status = 'active'
      )
      AND EXISTS (
          SELECT 1 FROM catalog.product_images im
          WHERE im.product_id = p.id AND im.status = 'active'
            AND im.archived_at IS NULL
      )
      AND EXISTS (
          SELECT 1 FROM catalog.product_variants v
          WHERE v.product_id = p.id AND v.is_default AND v.status = 'active'
      )
      AND EXISTS (
          SELECT 1 FROM catalog.product_variants v
          JOIN catalog.listings l ON l.variant_id = v.id
          WHERE v.product_id = p.id AND v.is_default AND v.status = 'active'
            AND l.status IN ('draft', 'active')
            AND l.price IS NOT NULL AND l.currency IS NOT NULL
            AND l.availability <> 'unknown'
      )
    RETURNING p.id
), activated AS (
    UPDATE catalog.listings l
    SET status = 'active', updated_at = now()
    FROM catalog.product_variants v, published p
    WHERE l.variant_id = v.id AND v.product_id = p.id AND v.status = 'active'
      AND l.status = 'draft' AND l.price IS NOT NULL AND l.currency IS NOT NULL
      AND l.availability <> 'unknown'
    RETURNING l.id
)
SELECT id::text AS published_id FROM published \gset
\if :{?published_id}
\else
    \echo 'Owner publication failed'
    SELECT 1/0;
\endif

RESET ROLE;
SET ROLE sahulat_assistant_reader;
SELECT EXISTS (
    SELECT 1 FROM catalog.products p
    WHERE p.id = :'product_id'::uuid AND p.vendor_id = :'vendor_id'::uuid
      AND p.name = 'Test draft' AND p.description = 'Database-backed draft test'
      AND p.status = 'published'
      AND EXISTS (
          SELECT 1 FROM iam.vendor_memberships m
          JOIN iam.users u ON u.id = m.user_id
          JOIN catalog.vendors v ON v.id = m.vendor_id
          WHERE m.user_id = :'editor_id'::uuid AND m.vendor_id = p.vendor_id
            AND m.status = 'active' AND u.status = 'active' AND v.status = 'active'
      )
) AS read_after_write_ok \gset
\if :read_after_write_ok
\else
    \echo 'Reader could not see the product after publication'
    SELECT 1/0;
\endif
SELECT EXISTS (
    SELECT 1 FROM catalog.listings l
    JOIN catalog.product_variants v ON v.id = l.variant_id
    WHERE l.id = :'listing_id'::uuid AND v.id = :'variant_id'::uuid
      AND v.product_id = :'product_id'::uuid
      AND l.price = 1999.00 AND l.currency = 'PKR'
      AND l.availability = 'in_stock' AND l.status = 'active'
) AS listing_read_after_write_ok \gset
\if :listing_read_after_write_ok
\else
    \echo 'Reader could not see the new listing'
    SELECT 1/0;
\endif
SELECT EXISTS (
    SELECT 1 FROM inventory.inventory_balances i
    WHERE i.listing_id = :'listing_id'::uuid
      AND i.on_hand_quantity = 5 AND i.reserved_quantity = 0
) AS stock_read_after_write_ok \gset
\if :stock_read_after_write_ok
\else
    \echo 'Reader could not see the reported stock'
    SELECT 1/0;
\endif
SELECT EXISTS (
    SELECT 1 FROM catalog.products p
    WHERE p.id = :'product_id'::uuid AND p.status = 'published'
      AND p.published_at IS NOT NULL AND p.category_id = :'category_id'::uuid
) AS published_read_after_write_ok \gset
\if :published_read_after_write_ok
\else
    \echo 'Reader could not see the published product'
    SELECT 1/0;
\endif
SELECT EXISTS (
    SELECT 1 FROM catalog.product_images im
    WHERE im.id = :'image_id'::uuid AND im.product_id = :'product_id'::uuid
      AND im.status = 'active' AND im.mime_type = 'image/png'
      AND im.width = 320 AND im.height = 240
) AS image_read_after_write_ok \gset
\if :image_read_after_write_ok
\else
    \echo 'Reader could not see the new image metadata'
    SELECT 1/0;
\endif
RESET ROLE;

ROLLBACK;
\echo 'Catalog draft writer integration smoke passed; fixture transaction rolled back.'
