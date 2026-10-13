-- Idempotent controlled taxonomy seed. Apply explicitly after catalog migration 001.
BEGIN;

INSERT INTO catalog.categories (name, slug, sort_order)
VALUES ('Women''s Clothing', 'womens-clothing', 10),
       ('Accessories', 'accessories', 40)
ON CONFLICT (slug) DO NOTHING;

INSERT INTO catalog.categories (parent_id, name, slug, sort_order)
SELECT parent.id, child.name, child.slug, child.sort_order
FROM catalog.categories parent
CROSS JOIN (VALUES
    ('Unstitched', 'unstitched', 20),
    ('Ready-to-Wear', 'ready-to-wear', 30)
) AS child(name, slug, sort_order)
WHERE parent.slug = 'womens-clothing'
ON CONFLICT (slug) DO NOTHING;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM catalog.categories
        WHERE slug = 'womens-clothing' AND name = 'Women''s Clothing'
          AND status = 'active' AND parent_id IS NULL
    ) OR NOT EXISTS (
        SELECT 1 FROM catalog.categories
        WHERE slug = 'accessories' AND name = 'Accessories'
          AND status = 'active' AND parent_id IS NULL
    ) OR EXISTS (
        SELECT 1 FROM (VALUES
            ('unstitched', 'Unstitched'),
            ('ready-to-wear', 'Ready-to-Wear')
        ) AS expected(slug, name)
        WHERE NOT EXISTS (
            SELECT 1 FROM catalog.categories child
            JOIN catalog.categories parent ON parent.id = child.parent_id
            WHERE child.slug = expected.slug AND child.name = expected.name
              AND child.status = 'active' AND parent.slug = 'womens-clothing'
        )
    ) THEN
        RAISE EXCEPTION 'Initial apparel category taxonomy conflicts with existing rows';
    END IF;
END $$;

COMMIT;
