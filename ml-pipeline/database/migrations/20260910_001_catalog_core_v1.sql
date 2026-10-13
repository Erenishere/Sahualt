\set ON_ERROR_STOP on

\if :{?migration_id}
\else
  \echo 'migration_id is required'
  \quit 2
\endif

\if :{?migration_checksum}
\else
  \echo 'migration_checksum is required'
  \quit 2
\endif

BEGIN;

SELECT pg_advisory_xact_lock(hashtextextended('sahulat_ai.schema_migrations', 0));

CREATE SCHEMA IF NOT EXISTS integration;

CREATE TABLE IF NOT EXISTS integration.schema_migrations (
    migration_id text PRIMARY KEY,
    checksum varchar(64) NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now(),
    postgres_version text NOT NULL,
    CONSTRAINT ck_schema_migrations_id_not_blank
        CHECK (btrim(migration_id) <> ''),
    CONSTRAINT ck_schema_migrations_checksum_sha256
        CHECK (checksum ~ '^[0-9a-f]{64}$')
);

SELECT EXISTS (
    SELECT 1
    FROM integration.schema_migrations
    WHERE migration_id = :'migration_id'
) AS migration_applied \gset

\if :migration_applied
  SELECT checksum = :'migration_checksum' AS migration_checksum_matches
  FROM integration.schema_migrations
  WHERE migration_id = :'migration_id' \gset

  \if :migration_checksum_matches
    \echo 'Migration already applied with matching checksum:' :migration_id
  \else
    \echo 'Migration checksum mismatch:' :migration_id
    ROLLBACK;
    \quit 3
  \endif
\else

CREATE SCHEMA iam;
CREATE SCHEMA catalog;
CREATE SCHEMA inventory;
CREATE SCHEMA audit;

CREATE TABLE iam.users (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    email text NOT NULL,
    email_normalized text NOT NULL,
    password_hash text NOT NULL,
    display_name text NOT NULL,
    status text NOT NULL DEFAULT 'pending',
    email_verified_at timestamptz,
    last_login_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    archived_at timestamptz,
    CONSTRAINT uq_users_email_normalized UNIQUE (email_normalized),
    CONSTRAINT ck_users_email_not_blank CHECK (btrim(email) <> ''),
    CONSTRAINT ck_users_email_normalized
        CHECK (
            btrim(email_normalized) <> ''
            AND email_normalized = lower(btrim(email_normalized))
        ),
    CONSTRAINT ck_users_password_hash_argon2id
        CHECK (password_hash LIKE '$argon2id$%'),
    CONSTRAINT ck_users_display_name_not_blank CHECK (btrim(display_name) <> ''),
    CONSTRAINT ck_users_status
        CHECK (status IN ('pending', 'active', 'suspended', 'archived'))
);

CREATE TABLE catalog.vendors (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    display_name text NOT NULL,
    legal_name text,
    slug text NOT NULL,
    status text NOT NULL DEFAULT 'pending',
    created_by_user_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    archived_at timestamptz,
    CONSTRAINT uq_vendors_slug UNIQUE (slug),
    CONSTRAINT fk_vendors_created_by_user
        FOREIGN KEY (created_by_user_id)
        REFERENCES iam.users (id)
        ON DELETE SET NULL,
    CONSTRAINT ck_vendors_display_name_not_blank CHECK (btrim(display_name) <> ''),
    CONSTRAINT ck_vendors_legal_name_not_blank
        CHECK (legal_name IS NULL OR btrim(legal_name) <> ''),
    CONSTRAINT ck_vendors_slug
        CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    CONSTRAINT ck_vendors_status
        CHECK (status IN ('pending', 'active', 'suspended', 'archived'))
);

CREATE TABLE iam.vendor_memberships (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    vendor_id uuid NOT NULL,
    user_id uuid NOT NULL,
    role text NOT NULL,
    status text NOT NULL DEFAULT 'pending',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_vendor_memberships_vendor_user UNIQUE (vendor_id, user_id),
    CONSTRAINT fk_vendor_memberships_vendor
        FOREIGN KEY (vendor_id)
        REFERENCES catalog.vendors (id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_vendor_memberships_user
        FOREIGN KEY (user_id)
        REFERENCES iam.users (id)
        ON DELETE RESTRICT,
    CONSTRAINT ck_vendor_memberships_role
        CHECK (role IN ('owner', 'manager', 'staff', 'viewer')),
    CONSTRAINT ck_vendor_memberships_status
        CHECK (status IN ('pending', 'active', 'suspended', 'revoked'))
);

CREATE TABLE catalog.categories (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    parent_id uuid,
    name text NOT NULL,
    slug text NOT NULL,
    status text NOT NULL DEFAULT 'active',
    sort_order integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    archived_at timestamptz,
    CONSTRAINT uq_categories_slug UNIQUE (slug),
    CONSTRAINT fk_categories_parent
        FOREIGN KEY (parent_id)
        REFERENCES catalog.categories (id)
        ON DELETE RESTRICT,
    CONSTRAINT ck_categories_name_not_blank CHECK (btrim(name) <> ''),
    CONSTRAINT ck_categories_slug
        CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    CONSTRAINT ck_categories_status
        CHECK (status IN ('active', 'inactive', 'archived')),
    CONSTRAINT ck_categories_sort_order_non_negative CHECK (sort_order >= 0),
    CONSTRAINT ck_categories_not_own_parent CHECK (parent_id IS NULL OR parent_id <> id)
);

CREATE TABLE catalog.products (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    vendor_id uuid NOT NULL,
    category_id uuid,
    name text NOT NULL,
    description text NOT NULL,
    brand_name text,
    status text NOT NULL DEFAULT 'draft',
    published_at timestamptz,
    created_by_user_id uuid,
    updated_by_user_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    archived_at timestamptz,
    CONSTRAINT fk_products_vendor
        FOREIGN KEY (vendor_id)
        REFERENCES catalog.vendors (id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_products_category
        FOREIGN KEY (category_id)
        REFERENCES catalog.categories (id)
        ON DELETE SET NULL,
    CONSTRAINT fk_products_created_by_user
        FOREIGN KEY (created_by_user_id)
        REFERENCES iam.users (id)
        ON DELETE SET NULL,
    CONSTRAINT fk_products_updated_by_user
        FOREIGN KEY (updated_by_user_id)
        REFERENCES iam.users (id)
        ON DELETE SET NULL,
    CONSTRAINT ck_products_name_not_blank CHECK (btrim(name) <> ''),
    CONSTRAINT ck_products_description_not_blank CHECK (btrim(description) <> ''),
    CONSTRAINT ck_products_brand_name_not_blank
        CHECK (brand_name IS NULL OR btrim(brand_name) <> ''),
    CONSTRAINT ck_products_status
        CHECK (status IN ('draft', 'published', 'paused', 'archived')),
    CONSTRAINT ck_products_published_at
        CHECK (status <> 'published' OR published_at IS NOT NULL)
);

CREATE TABLE catalog.product_variants (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    product_id uuid NOT NULL,
    variant_code text NOT NULL,
    sku text,
    color text,
    size text,
    status text NOT NULL DEFAULT 'draft',
    is_default boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    archived_at timestamptz,
    CONSTRAINT uq_product_variants_id_product UNIQUE (id, product_id),
    CONSTRAINT fk_product_variants_product
        FOREIGN KEY (product_id)
        REFERENCES catalog.products (id)
        ON DELETE RESTRICT,
    CONSTRAINT ck_product_variants_code_not_blank CHECK (btrim(variant_code) <> ''),
    CONSTRAINT ck_product_variants_sku_not_blank
        CHECK (sku IS NULL OR btrim(sku) <> ''),
    CONSTRAINT ck_product_variants_color_not_blank
        CHECK (color IS NULL OR btrim(color) <> ''),
    CONSTRAINT ck_product_variants_size_not_blank
        CHECK (size IS NULL OR btrim(size) <> ''),
    CONSTRAINT ck_product_variants_status
        CHECK (status IN ('draft', 'active', 'paused', 'archived'))
);

CREATE TABLE catalog.listings (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    variant_id uuid NOT NULL,
    price numeric(12, 2),
    currency varchar(3),
    availability text NOT NULL DEFAULT 'unknown',
    status text NOT NULL DEFAULT 'draft',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    archived_at timestamptz,
    CONSTRAINT fk_listings_variant
        FOREIGN KEY (variant_id)
        REFERENCES catalog.product_variants (id)
        ON DELETE RESTRICT,
    CONSTRAINT ck_listings_price_non_negative CHECK (price IS NULL OR price >= 0),
    CONSTRAINT ck_listings_currency
        CHECK (currency IS NULL OR currency ~ '^[A-Z]{3}$'),
    CONSTRAINT ck_listings_availability
        CHECK (
            availability IN (
                'unknown', 'in_stock', 'out_of_stock', 'preorder', 'unavailable'
            )
        ),
    CONSTRAINT ck_listings_status
        CHECK (status IN ('draft', 'active', 'paused', 'archived')),
    CONSTRAINT ck_listings_active_commercial_state
        CHECK (
            status <> 'active'
            OR (
                price IS NOT NULL
                AND currency IS NOT NULL
                AND availability <> 'unknown'
            )
        )
);

CREATE TABLE inventory.inventory_balances (
    listing_id uuid PRIMARY KEY,
    on_hand_quantity integer,
    reserved_quantity integer NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_inventory_balances_listing
        FOREIGN KEY (listing_id)
        REFERENCES catalog.listings (id)
        ON DELETE RESTRICT,
    CONSTRAINT ck_inventory_on_hand_non_negative
        CHECK (on_hand_quantity IS NULL OR on_hand_quantity >= 0),
    CONSTRAINT ck_inventory_reserved_non_negative CHECK (reserved_quantity >= 0),
    CONSTRAINT ck_inventory_reserved_within_on_hand
        CHECK (
            on_hand_quantity IS NULL
            OR reserved_quantity <= on_hand_quantity
        )
);

CREATE TABLE catalog.product_images (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    product_id uuid NOT NULL,
    variant_id uuid,
    storage_key text NOT NULL,
    source_url text,
    mime_type text NOT NULL,
    width integer,
    height integer,
    sha256 varchar(64),
    sort_order integer NOT NULL DEFAULT 0,
    is_primary boolean NOT NULL DEFAULT false,
    status text NOT NULL DEFAULT 'pending',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    archived_at timestamptz,
    CONSTRAINT uq_product_images_storage_key UNIQUE (storage_key),
    CONSTRAINT fk_product_images_product
        FOREIGN KEY (product_id)
        REFERENCES catalog.products (id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_product_images_variant_product
        FOREIGN KEY (variant_id, product_id)
        REFERENCES catalog.product_variants (id, product_id)
        ON DELETE RESTRICT,
    CONSTRAINT ck_product_images_storage_key_not_blank CHECK (btrim(storage_key) <> ''),
    CONSTRAINT ck_product_images_source_url_not_blank
        CHECK (source_url IS NULL OR btrim(source_url) <> ''),
    CONSTRAINT ck_product_images_mime_type_not_blank CHECK (btrim(mime_type) <> ''),
    CONSTRAINT ck_product_images_width_positive CHECK (width IS NULL OR width > 0),
    CONSTRAINT ck_product_images_height_positive CHECK (height IS NULL OR height > 0),
    CONSTRAINT ck_product_images_sha256
        CHECK (sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_product_images_sort_order_non_negative CHECK (sort_order >= 0),
    CONSTRAINT ck_product_images_status
        CHECK (status IN ('pending', 'active', 'rejected', 'archived'))
);

CREATE TABLE catalog.product_external_refs (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    product_id uuid NOT NULL,
    source_system text NOT NULL,
    external_product_id text NOT NULL,
    source_checksum varchar(64),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_product_external_refs_source_external
        UNIQUE (source_system, external_product_id),
    CONSTRAINT fk_product_external_refs_product
        FOREIGN KEY (product_id)
        REFERENCES catalog.products (id)
        ON DELETE CASCADE,
    CONSTRAINT ck_product_external_refs_source_system_not_blank
        CHECK (btrim(source_system) <> ''),
    CONSTRAINT ck_product_external_refs_external_id_not_blank
        CHECK (btrim(external_product_id) <> ''),
    CONSTRAINT ck_product_external_refs_source_checksum
        CHECK (
            source_checksum IS NULL
            OR source_checksum ~ '^[0-9a-f]{64}$'
        )
);

CREATE TABLE catalog.image_external_refs (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    image_id uuid NOT NULL,
    source_system text NOT NULL,
    external_image_id text NOT NULL,
    source_path text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_image_external_refs_source_external
        UNIQUE (source_system, external_image_id),
    CONSTRAINT fk_image_external_refs_image
        FOREIGN KEY (image_id)
        REFERENCES catalog.product_images (id)
        ON DELETE CASCADE,
    CONSTRAINT ck_image_external_refs_source_system_not_blank
        CHECK (btrim(source_system) <> ''),
    CONSTRAINT ck_image_external_refs_external_id_not_blank
        CHECK (btrim(external_image_id) <> ''),
    CONSTRAINT ck_image_external_refs_source_path_portable
        CHECK (
            source_path IS NULL
            OR (
                btrim(source_path) <> ''
                AND left(source_path, 1) NOT IN ('/', E'\\')
                AND source_path !~ '^[A-Za-z]:'
            )
        )
);

CREATE TABLE integration.outbox_events (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    event_type text NOT NULL,
    aggregate_type text NOT NULL,
    aggregate_id uuid NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL DEFAULT 'pending',
    attempt_count integer NOT NULL DEFAULT 0,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    processed_at timestamptz,
    last_error text,
    CONSTRAINT ck_outbox_events_event_type_not_blank CHECK (btrim(event_type) <> ''),
    CONSTRAINT ck_outbox_events_aggregate_type_not_blank
        CHECK (btrim(aggregate_type) <> ''),
    CONSTRAINT ck_outbox_events_payload_object
        CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT ck_outbox_events_status
        CHECK (status IN ('pending', 'processing', 'processed', 'failed')),
    CONSTRAINT ck_outbox_events_attempt_count_non_negative CHECK (attempt_count >= 0),
    CONSTRAINT ck_outbox_events_processed_at
        CHECK (status <> 'processed' OR processed_at IS NOT NULL),
    CONSTRAINT ck_outbox_events_last_error_not_blank
        CHECK (last_error IS NULL OR btrim(last_error) <> '')
);

CREATE TABLE audit.audit_log (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    actor_user_id uuid,
    vendor_id uuid,
    entity_type text NOT NULL,
    entity_id uuid NOT NULL,
    action text NOT NULL,
    before_data jsonb,
    after_data jsonb,
    request_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_audit_log_actor_user
        FOREIGN KEY (actor_user_id)
        REFERENCES iam.users (id)
        ON DELETE SET NULL,
    CONSTRAINT fk_audit_log_vendor
        FOREIGN KEY (vendor_id)
        REFERENCES catalog.vendors (id)
        ON DELETE SET NULL,
    CONSTRAINT ck_audit_log_entity_type_not_blank CHECK (btrim(entity_type) <> ''),
    CONSTRAINT ck_audit_log_action_not_blank CHECK (btrim(action) <> ''),
    CONSTRAINT ck_audit_log_before_data_object
        CHECK (before_data IS NULL OR jsonb_typeof(before_data) = 'object'),
    CONSTRAINT ck_audit_log_after_data_object
        CHECK (after_data IS NULL OR jsonb_typeof(after_data) = 'object')
);

CREATE INDEX ix_vendors_created_by_user_id
    ON catalog.vendors (created_by_user_id);
CREATE INDEX ix_vendor_memberships_user_id
    ON iam.vendor_memberships (user_id);
CREATE INDEX ix_categories_parent_id
    ON catalog.categories (parent_id);
CREATE INDEX ix_products_vendor_status
    ON catalog.products (vendor_id, status);
CREATE INDEX ix_products_category_id
    ON catalog.products (category_id);
CREATE INDEX ix_products_created_by_user_id
    ON catalog.products (created_by_user_id);
CREATE INDEX ix_products_updated_by_user_id
    ON catalog.products (updated_by_user_id);
CREATE INDEX ix_product_variants_product_id
    ON catalog.product_variants (product_id);
CREATE UNIQUE INDEX uq_product_variants_product_variant_code_active
    ON catalog.product_variants (product_id, variant_code)
    WHERE archived_at IS NULL;
CREATE UNIQUE INDEX uq_product_variants_default_active
    ON catalog.product_variants (product_id)
    WHERE is_default = true AND archived_at IS NULL;
CREATE INDEX ix_listings_variant_id
    ON catalog.listings (variant_id);
CREATE INDEX ix_listings_status_availability
    ON catalog.listings (status, availability);
CREATE INDEX ix_listings_currency_price
    ON catalog.listings (currency, price);
CREATE INDEX ix_product_images_product_sort_order
    ON catalog.product_images (product_id, sort_order);
CREATE INDEX ix_product_images_variant_id
    ON catalog.product_images (variant_id);
CREATE UNIQUE INDEX uq_product_images_primary_product
    ON catalog.product_images (product_id)
    WHERE is_primary = true AND variant_id IS NULL AND archived_at IS NULL;
CREATE UNIQUE INDEX uq_product_images_primary_variant
    ON catalog.product_images (variant_id)
    WHERE is_primary = true AND variant_id IS NOT NULL AND archived_at IS NULL;
CREATE INDEX ix_product_external_refs_product_id
    ON catalog.product_external_refs (product_id);
CREATE INDEX ix_image_external_refs_image_id
    ON catalog.image_external_refs (image_id);
CREATE INDEX ix_outbox_events_pending
    ON integration.outbox_events (occurred_at, id)
    WHERE status = 'pending' AND processed_at IS NULL;
CREATE INDEX ix_audit_log_actor_user_id
    ON audit.audit_log (actor_user_id);
CREATE INDEX ix_audit_log_vendor_id_created_at
    ON audit.audit_log (vendor_id, created_at);
CREATE INDEX ix_audit_log_entity
    ON audit.audit_log (entity_type, entity_id, created_at);

INSERT INTO integration.schema_migrations (
    migration_id,
    checksum,
    postgres_version
)
VALUES (
    :'migration_id',
    :'migration_checksum',
    current_setting('server_version')
);

\endif

COMMIT;
