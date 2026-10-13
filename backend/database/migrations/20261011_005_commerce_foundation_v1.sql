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

SELECT EXISTS (
    SELECT 1 FROM integration.schema_migrations WHERE migration_id = :'migration_id'
) AS migration_applied \gset

\if :migration_applied
  SELECT checksum = :'migration_checksum' AS migration_checksum_matches
  FROM integration.schema_migrations WHERE migration_id = :'migration_id' \gset
  \if :migration_checksum_matches
    \echo 'Migration already applied with matching checksum:' :migration_id
  \else
    \echo 'Migration checksum mismatch:' :migration_id
    ROLLBACK;
    \quit 3
  \endif
\else

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM integration.schema_migrations
        WHERE migration_id = '20261011_004_backend_business_baseline_v1'
    ) THEN
        RAISE EXCEPTION 'backend business baseline migration 004 is required';
    END IF;
END $$;

CREATE SCHEMA commerce;

CREATE TABLE iam.user_roles (
    user_id uuid NOT NULL,
    role text NOT NULL,
    status text NOT NULL DEFAULT 'active',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, role),
    CONSTRAINT fk_user_roles_user FOREIGN KEY (user_id)
        REFERENCES iam.users (id) ON DELETE RESTRICT,
    CONSTRAINT ck_user_roles_role CHECK (role IN ('customer', 'platform_admin')),
    CONSTRAINT ck_user_roles_status CHECK (status IN ('active', 'revoked'))
);

CREATE TABLE iam.customer_profiles (
    user_id uuid PRIMARY KEY,
    phone text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_customer_profiles_user FOREIGN KEY (user_id)
        REFERENCES iam.users (id) ON DELETE RESTRICT,
    CONSTRAINT ck_customer_profiles_phone CHECK (
        phone IS NULL OR (btrim(phone) <> '' AND length(phone) <= 32)
    )
);

CREATE TABLE iam.customer_addresses (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    user_id uuid NOT NULL,
    label text NOT NULL DEFAULT 'Home',
    recipient_name text NOT NULL,
    phone text NOT NULL,
    address_line1 text NOT NULL,
    address_line2 text,
    city text NOT NULL,
    province text,
    postal_code text,
    is_default boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    archived_at timestamptz,
    CONSTRAINT fk_customer_addresses_user FOREIGN KEY (user_id)
        REFERENCES iam.users (id) ON DELETE RESTRICT,
    CONSTRAINT ck_customer_addresses_text CHECK (
        btrim(label) <> '' AND length(label) <= 50
        AND btrim(recipient_name) <> '' AND length(recipient_name) <= 200
        AND btrim(phone) <> '' AND length(phone) <= 32
        AND btrim(address_line1) <> '' AND length(address_line1) <= 300
        AND (address_line2 IS NULL OR (btrim(address_line2) <> '' AND length(address_line2) <= 300))
        AND btrim(city) <> '' AND length(city) <= 100
        AND (province IS NULL OR (btrim(province) <> '' AND length(province) <= 100))
        AND (postal_code IS NULL OR (btrim(postal_code) <> '' AND length(postal_code) <= 20))
    )
);
CREATE UNIQUE INDEX uq_customer_addresses_default
    ON iam.customer_addresses (user_id) WHERE is_default AND archived_at IS NULL;
CREATE INDEX ix_customer_addresses_user
    ON iam.customer_addresses (user_id, created_at, id) WHERE archived_at IS NULL;

ALTER TABLE catalog.vendors
    ADD COLUMN description text,
    ADD COLUMN allow_customer_offers boolean NOT NULL DEFAULT false,
    ADD CONSTRAINT ck_vendors_description CHECK (
        description IS NULL OR (btrim(description) <> '' AND length(description) <= 2000)
    );

ALTER TABLE catalog.listings
    ADD COLUMN allow_customer_offers boolean NOT NULL DEFAULT false;

CREATE SEQUENCE commerce.offer_number_seq START WITH 1000;
CREATE SEQUENCE commerce.order_number_seq START WITH 1000;

CREATE TABLE commerce.offers (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    public_offer_number text NOT NULL DEFAULT
        ('OFF-' || lpad(nextval('commerce.offer_number_seq')::text, 8, '0')),
    customer_user_id uuid NOT NULL,
    vendor_id uuid NOT NULL,
    listing_id uuid NOT NULL,
    currency varchar(3) NOT NULL,
    listed_price numeric(12,2) NOT NULL,
    offered_price numeric(12,2) NOT NULL,
    counter_price numeric(12,2),
    status text NOT NULL DEFAULT 'pending',
    customer_message text,
    expires_at timestamptz NOT NULL,
    accepted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_offers_public_number UNIQUE (public_offer_number),
    CONSTRAINT fk_offers_customer FOREIGN KEY (customer_user_id)
        REFERENCES iam.users (id) ON DELETE RESTRICT,
    CONSTRAINT fk_offers_vendor FOREIGN KEY (vendor_id)
        REFERENCES catalog.vendors (id) ON DELETE RESTRICT,
    CONSTRAINT fk_offers_listing FOREIGN KEY (listing_id)
        REFERENCES catalog.listings (id) ON DELETE RESTRICT,
    CONSTRAINT ck_offers_currency CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT ck_offers_prices CHECK (
        listed_price > 0 AND offered_price > 0 AND offered_price < listed_price
        AND (counter_price IS NULL OR (counter_price > offered_price AND counter_price <= listed_price))
    ),
    CONSTRAINT ck_offers_status CHECK (
        status IN ('pending', 'countered', 'accepted', 'rejected', 'withdrawn', 'expired', 'converted')
    ),
    CONSTRAINT ck_offers_message CHECK (
        customer_message IS NULL OR (btrim(customer_message) <> '' AND length(customer_message) <= 500)
    ),
    CONSTRAINT ck_offers_expiry CHECK (expires_at > created_at),
    CONSTRAINT ck_offers_accepted_at CHECK (
        status NOT IN ('accepted', 'converted') OR accepted_at IS NOT NULL
    )
);
CREATE INDEX ix_offers_customer ON commerce.offers
    (customer_user_id, created_at DESC, id DESC);
CREATE INDEX ix_offers_vendor ON commerce.offers
    (vendor_id, created_at DESC, id DESC);
CREATE INDEX ix_offers_listing ON commerce.offers (listing_id, status);
CREATE UNIQUE INDEX uq_offers_customer_listing_open ON commerce.offers
    (customer_user_id, listing_id)
    WHERE status IN ('pending', 'countered', 'accepted');

CREATE TABLE commerce.orders (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    public_order_number text NOT NULL DEFAULT
        ('SAH-' || lpad(nextval('commerce.order_number_seq')::text, 8, '0')),
    customer_user_id uuid NOT NULL,
    vendor_id uuid NOT NULL,
    accepted_offer_id uuid,
    idempotency_key uuid NOT NULL,
    idempotency_fingerprint varchar(64) NOT NULL,
    status text NOT NULL DEFAULT 'placed',
    payment_method text NOT NULL,
    payment_status text NOT NULL,
    currency varchar(3) NOT NULL,
    subtotal numeric(12,2) NOT NULL,
    discount_total numeric(12,2) NOT NULL DEFAULT 0,
    delivery_total numeric(12,2) NOT NULL DEFAULT 0,
    total numeric(12,2) NOT NULL,
    delivery_name text NOT NULL,
    delivery_phone text NOT NULL,
    delivery_address_line1 text NOT NULL,
    delivery_address_line2 text,
    delivery_city text NOT NULL,
    delivery_province text,
    delivery_postal_code text,
    placed_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    cancelled_at timestamptz,
    completed_at timestamptz,
    CONSTRAINT uq_orders_public_number UNIQUE (public_order_number),
    CONSTRAINT uq_orders_customer_idempotency UNIQUE (customer_user_id, idempotency_key),
    CONSTRAINT uq_orders_accepted_offer UNIQUE (accepted_offer_id),
    CONSTRAINT fk_orders_customer FOREIGN KEY (customer_user_id)
        REFERENCES iam.users (id) ON DELETE RESTRICT,
    CONSTRAINT fk_orders_vendor FOREIGN KEY (vendor_id)
        REFERENCES catalog.vendors (id) ON DELETE RESTRICT,
    CONSTRAINT fk_orders_offer FOREIGN KEY (accepted_offer_id)
        REFERENCES commerce.offers (id) ON DELETE RESTRICT,
    CONSTRAINT ck_orders_status CHECK (
        status IN ('placed', 'confirmed', 'processing', 'shipped', 'completed', 'cancelled')
    ),
    CONSTRAINT ck_orders_payment_method CHECK (payment_method IN ('cash_on_delivery')),
    CONSTRAINT ck_orders_payment_status CHECK (
        payment_status IN ('cod_due', 'paid', 'failed', 'refunded')
    ),
    CONSTRAINT ck_orders_currency CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT ck_orders_idempotency_fingerprint CHECK (idempotency_fingerprint ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_orders_totals CHECK (
        subtotal >= 0 AND discount_total >= 0 AND delivery_total >= 0 AND total >= 0
        AND discount_total <= subtotal
        AND total = subtotal - discount_total + delivery_total
    ),
    CONSTRAINT ck_orders_delivery CHECK (
        btrim(delivery_name) <> '' AND length(delivery_name) <= 200
        AND btrim(delivery_phone) <> '' AND length(delivery_phone) <= 32
        AND btrim(delivery_address_line1) <> '' AND length(delivery_address_line1) <= 300
        AND (delivery_address_line2 IS NULL OR (btrim(delivery_address_line2) <> '' AND length(delivery_address_line2) <= 300))
        AND btrim(delivery_city) <> '' AND length(delivery_city) <= 100
        AND (delivery_province IS NULL OR (btrim(delivery_province) <> '' AND length(delivery_province) <= 100))
        AND (delivery_postal_code IS NULL OR (btrim(delivery_postal_code) <> '' AND length(delivery_postal_code) <= 20))
    ),
    CONSTRAINT ck_orders_terminal_times CHECK (
        (status <> 'cancelled' OR cancelled_at IS NOT NULL)
        AND (status <> 'completed' OR completed_at IS NOT NULL)
    )
);
CREATE INDEX ix_orders_customer ON commerce.orders
    (customer_user_id, placed_at DESC, id DESC);
CREATE INDEX ix_orders_vendor ON commerce.orders
    (vendor_id, placed_at DESC, id DESC);
CREATE INDEX ix_orders_vendor_status ON commerce.orders
    (vendor_id, status, placed_at DESC, id DESC);

CREATE TABLE commerce.order_items (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    order_id uuid NOT NULL,
    listing_id uuid NOT NULL,
    product_id uuid NOT NULL,
    variant_id uuid NOT NULL,
    item_name text NOT NULL,
    variant_code text NOT NULL,
    sku text,
    unit_price numeric(12,2) NOT NULL,
    currency varchar(3) NOT NULL,
    quantity integer NOT NULL,
    discount_total numeric(12,2) NOT NULL DEFAULT 0,
    line_total numeric(12,2) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_order_items_order FOREIGN KEY (order_id)
        REFERENCES commerce.orders (id) ON DELETE RESTRICT,
    CONSTRAINT fk_order_items_listing FOREIGN KEY (listing_id)
        REFERENCES catalog.listings (id) ON DELETE RESTRICT,
    CONSTRAINT fk_order_items_product FOREIGN KEY (product_id)
        REFERENCES catalog.products (id) ON DELETE RESTRICT,
    CONSTRAINT fk_order_items_variant FOREIGN KEY (variant_id)
        REFERENCES catalog.product_variants (id) ON DELETE RESTRICT,
    CONSTRAINT ck_order_items_text CHECK (
        btrim(item_name) <> '' AND length(item_name) <= 200
        AND btrim(variant_code) <> '' AND length(variant_code) <= 80
        AND (sku IS NULL OR (btrim(sku) <> '' AND length(sku) <= 200))
    ),
    CONSTRAINT ck_order_items_amounts CHECK (
        unit_price > 0 AND quantity > 0 AND quantity <= 100
        AND discount_total >= 0 AND discount_total <= unit_price * quantity
        AND line_total = unit_price * quantity - discount_total
    ),
    CONSTRAINT ck_order_items_currency CHECK (currency ~ '^[A-Z]{3}$')
);
CREATE INDEX ix_order_items_order ON commerce.order_items (order_id, id);
CREATE INDEX ix_order_items_listing ON commerce.order_items (listing_id, order_id);

CREATE TABLE inventory.inventory_reservations (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    order_item_id uuid NOT NULL,
    listing_id uuid NOT NULL,
    quantity integer NOT NULL,
    status text NOT NULL DEFAULT 'active',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    released_at timestamptz,
    consumed_at timestamptz,
    CONSTRAINT uq_inventory_reservations_order_item UNIQUE (order_item_id),
    CONSTRAINT fk_inventory_reservations_order_item FOREIGN KEY (order_item_id)
        REFERENCES commerce.order_items (id) ON DELETE RESTRICT,
    CONSTRAINT fk_inventory_reservations_listing FOREIGN KEY (listing_id)
        REFERENCES catalog.listings (id) ON DELETE RESTRICT,
    CONSTRAINT ck_inventory_reservations_quantity CHECK (quantity > 0),
    CONSTRAINT ck_inventory_reservations_status CHECK (status IN ('active', 'released', 'consumed')),
    CONSTRAINT ck_inventory_reservations_times CHECK (
        (status <> 'released' OR released_at IS NOT NULL)
        AND (status <> 'consumed' OR consumed_at IS NOT NULL)
    )
);
CREATE INDEX ix_inventory_reservations_listing_status
    ON inventory.inventory_reservations (listing_id, status);

CREATE TABLE commerce.payment_events (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    order_id uuid NOT NULL,
    provider text NOT NULL,
    provider_event_id text NOT NULL,
    event_type text NOT NULL,
    amount numeric(12,2) NOT NULL,
    currency varchar(3) NOT NULL,
    occurred_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_payment_events_provider_event UNIQUE (provider, provider_event_id),
    CONSTRAINT fk_payment_events_order FOREIGN KEY (order_id)
        REFERENCES commerce.orders (id) ON DELETE RESTRICT,
    CONSTRAINT ck_payment_events_text CHECK (
        btrim(provider) <> '' AND btrim(provider_event_id) <> '' AND btrim(event_type) <> ''
    ),
    CONSTRAINT ck_payment_events_amount CHECK (amount >= 0),
    CONSTRAINT ck_payment_events_currency CHECK (currency ~ '^[A-Z]{3}$')
);
CREATE INDEX ix_payment_events_order ON commerce.payment_events (order_id, occurred_at, id);

CREATE TABLE commerce.refund_events (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    order_id uuid NOT NULL,
    order_item_id uuid,
    provider_refund_id text NOT NULL,
    amount numeric(12,2) NOT NULL,
    currency varchar(3) NOT NULL,
    occurred_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_refund_events_provider_refund UNIQUE (provider_refund_id),
    CONSTRAINT fk_refund_events_order FOREIGN KEY (order_id)
        REFERENCES commerce.orders (id) ON DELETE RESTRICT,
    CONSTRAINT fk_refund_events_order_item FOREIGN KEY (order_item_id)
        REFERENCES commerce.order_items (id) ON DELETE RESTRICT,
    CONSTRAINT ck_refund_events_id CHECK (btrim(provider_refund_id) <> ''),
    CONSTRAINT ck_refund_events_amount CHECK (amount > 0),
    CONSTRAINT ck_refund_events_currency CHECK (currency ~ '^[A-Z]{3}$')
);
CREATE INDEX ix_refund_events_order ON commerce.refund_events (order_id, occurred_at, id);

CREATE FUNCTION commerce.enforce_offer_scope() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE listing_vendor_id uuid;
BEGIN
    SELECT p.vendor_id INTO listing_vendor_id
    FROM catalog.listings l
    JOIN catalog.product_variants pv ON pv.id = l.variant_id
    JOIN catalog.products p ON p.id = pv.product_id
    WHERE l.id = NEW.listing_id;
    IF listing_vendor_id IS NULL OR listing_vendor_id <> NEW.vendor_id THEN
        RAISE EXCEPTION 'offer listing does not belong to vendor' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER trg_offers_scope
    BEFORE INSERT OR UPDATE OF vendor_id, listing_id ON commerce.offers
    FOR EACH ROW EXECUTE FUNCTION commerce.enforce_offer_scope();

CREATE FUNCTION commerce.enforce_order_offer_scope() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE offer_customer_id uuid; offer_vendor_id uuid; offer_status text;
BEGIN
    IF NEW.accepted_offer_id IS NULL THEN RETURN NEW; END IF;
    SELECT customer_user_id, vendor_id, status
    INTO offer_customer_id, offer_vendor_id, offer_status
    FROM commerce.offers WHERE id = NEW.accepted_offer_id;
    IF offer_customer_id IS NULL OR offer_customer_id <> NEW.customer_user_id
       OR offer_vendor_id <> NEW.vendor_id OR offer_status <> 'accepted' THEN
        RAISE EXCEPTION 'accepted offer does not match order scope' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER trg_orders_offer_scope
    BEFORE INSERT OR UPDATE OF customer_user_id, vendor_id, accepted_offer_id ON commerce.orders
    FOR EACH ROW EXECUTE FUNCTION commerce.enforce_order_offer_scope();

CREATE FUNCTION commerce.enforce_order_item_scope() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE order_vendor_id uuid; order_currency varchar(3); listing_vendor_id uuid;
        listing_product_id uuid; listing_variant_id uuid;
BEGIN
    SELECT vendor_id, currency INTO order_vendor_id, order_currency
    FROM commerce.orders WHERE id = NEW.order_id;
    SELECT p.vendor_id, p.id, pv.id
    INTO listing_vendor_id, listing_product_id, listing_variant_id
    FROM catalog.listings l
    JOIN catalog.product_variants pv ON pv.id = l.variant_id
    JOIN catalog.products p ON p.id = pv.product_id
    WHERE l.id = NEW.listing_id;
    IF order_vendor_id IS NULL OR listing_vendor_id IS NULL
       OR order_vendor_id <> listing_vendor_id OR order_currency <> NEW.currency
       OR listing_product_id <> NEW.product_id OR listing_variant_id <> NEW.variant_id THEN
        RAISE EXCEPTION 'order item does not match order and listing scope' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER trg_order_items_scope
    BEFORE INSERT OR UPDATE OF order_id, listing_id, product_id, variant_id, currency
    ON commerce.order_items FOR EACH ROW EXECUTE FUNCTION commerce.enforce_order_item_scope();

CREATE FUNCTION commerce.enforce_order_transition() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.status = OLD.status THEN RETURN NEW; END IF;
    IF (OLD.status, NEW.status) NOT IN (
        ('placed', 'confirmed'), ('confirmed', 'processing'), ('processing', 'shipped'),
        ('shipped', 'completed'), ('placed', 'cancelled'), ('confirmed', 'cancelled'),
        ('processing', 'cancelled')
    ) THEN
        RAISE EXCEPTION 'invalid order status transition from % to %', OLD.status, NEW.status
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER trg_orders_transition
    BEFORE UPDATE OF status ON commerce.orders
    FOR EACH ROW EXECUTE FUNCTION commerce.enforce_order_transition();

INSERT INTO integration.schema_migrations (
    migration_id, checksum, postgres_version
) VALUES (
    :'migration_id', :'migration_checksum', current_setting('server_version')
);

\endif
COMMIT;
