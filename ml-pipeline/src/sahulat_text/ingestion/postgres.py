from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sahulat_database.migrations import DatabaseConfig, query_json, run_psql

from .canonical import (
    content_checksum,
    image_external_ref_uuid,
    image_projection,
    image_uuid,
    import_result_checksum,
    listing_uuid,
    product_external_ref_uuid,
    product_uuid,
    semantic_checksum,
    semantic_projection,
    variant_uuid,
    vendor_uuid,
)
from .contracts import CanonicalImportBatch

IMPORT_RESULT_MARKER = "FIXTURE_IMPORT_RESULT="


class CanonicalImportError(RuntimeError):
    """Raised when canonical database state conflicts with an import batch."""


@dataclass(frozen=True, slots=True)
class ImportExecution:
    start_state: dict[str, int]
    created: dict[str, int]
    end_state: dict[str, int]

    @property
    def is_no_op(self) -> bool:
        return all(value == 0 for value in self.created.values())


def _json_payload(value: Any, tag: str) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    delimiter = f"${tag}$"
    if delimiter in payload:
        raise CanonicalImportError("Import payload contains the SQL payload delimiter")
    return f"{delimiter}{payload}{delimiter}"


def _flatten_batch(batch: CanonicalImportBatch) -> dict[str, list[dict[str, Any]]]:
    vendor_id = vendor_uuid(batch.external_source)
    products: list[dict[str, Any]] = []
    variants: list[dict[str, Any]] = []
    listings: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []
    image_refs: list[dict[str, Any]] = []
    product_refs: list[dict[str, Any]] = []

    for product in batch.products:
        canonical_product_id = product_uuid(product)
        products.append(
            {
                "id": str(canonical_product_id),
                "vendor_id": str(vendor_id),
                "category_id": str(product.category_id) if product.category_id else None,
                "name": product.name,
                "description": product.description,
                "brand_name": product.brand_name,
                "status": product.status,
            }
        )
        product_refs.append(
            {
                "id": str(product_external_ref_uuid(product)),
                "product_id": str(canonical_product_id),
                "source_system": product.external_source,
                "external_product_id": product.external_product_id,
                "source_checksum": product.source_checksum,
            }
        )
        variant_ids: dict[str, str] = {}
        for variant in product.variants:
            canonical_variant_id = variant_uuid(product, variant.variant_code)
            variant_ids[variant.variant_code] = str(canonical_variant_id)
            variants.append(
                {
                    "id": str(canonical_variant_id),
                    "product_id": str(canonical_product_id),
                    "variant_code": variant.variant_code,
                    "sku": variant.sku,
                    "color": variant.color,
                    "size": variant.size,
                    "status": variant.status,
                    "is_default": variant.is_default,
                }
            )
            listings.append(
                {
                    "id": str(listing_uuid(product, variant.variant_code)),
                    "variant_id": str(canonical_variant_id),
                    "price": (
                        None
                        if variant.listing.price is None
                        else format(variant.listing.price, "f")
                    ),
                    "currency": variant.listing.currency,
                    "availability": variant.listing.availability,
                    "status": variant.listing.status,
                }
            )
        for image in product.images:
            canonical_image_id = image_uuid(product, image.external_image_id)
            images.append(
                {
                    "id": str(canonical_image_id),
                    "product_id": str(canonical_product_id),
                    "variant_id": (
                        variant_ids[image.variant_code] if image.variant_code is not None else None
                    ),
                    "storage_key": image.storage_key,
                    "mime_type": image.mime_type,
                    "width": image.width,
                    "height": image.height,
                    "sha256": image.sha256,
                    "sort_order": image.sort_order,
                    "is_primary": image.is_primary,
                    "status": "active",
                }
            )
            image_refs.append(
                {
                    "id": str(image_external_ref_uuid(product, image.external_image_id)),
                    "image_id": str(canonical_image_id),
                    "source_system": product.external_source,
                    "external_image_id": image.external_image_id,
                    "source_path": image.source_path,
                }
            )
    return {
        "vendor": [
            {
                "id": str(vendor_id),
                "display_name": batch.vendor_display_name,
                "slug": batch.vendor_slug,
                "source_system": batch.external_source,
            }
        ],
        "products": products,
        "product_refs": product_refs,
        "variants": variants,
        "listings": listings,
        "images": images,
        "image_refs": image_refs,
    }


def _import_sql(batch: CanonicalImportBatch) -> str:
    rows = _flatten_batch(batch)
    payloads = {name: _json_payload(value, f"fixture_{name}") for name, value in rows.items()}
    return f"""
\\set ON_ERROR_STOP on
BEGIN;
SELECT pg_advisory_xact_lock(hashtextextended('sahulat_ai.fixture_ingestion', 0));

CREATE TEMP TABLE _fixture_vendor (
    id uuid PRIMARY KEY,
    display_name text NOT NULL,
    slug text NOT NULL,
    source_system text NOT NULL
) ON COMMIT DROP;
INSERT INTO _fixture_vendor
SELECT * FROM jsonb_to_recordset({payloads["vendor"]}::jsonb)
    AS row(id uuid, display_name text, slug text, source_system text);

CREATE TEMP TABLE _fixture_products (
    id uuid PRIMARY KEY,
    vendor_id uuid NOT NULL,
    category_id uuid,
    name text NOT NULL,
    description text NOT NULL,
    brand_name text,
    status text NOT NULL
) ON COMMIT DROP;
INSERT INTO _fixture_products
SELECT * FROM jsonb_to_recordset({payloads["products"]}::jsonb)
    AS row(
        id uuid, vendor_id uuid, category_id uuid, name text, description text,
        brand_name text, status text
    );

CREATE TEMP TABLE _fixture_product_refs (
    id uuid PRIMARY KEY,
    product_id uuid NOT NULL,
    source_system text NOT NULL,
    external_product_id text NOT NULL,
    source_checksum varchar(64) NOT NULL
) ON COMMIT DROP;
INSERT INTO _fixture_product_refs
SELECT * FROM jsonb_to_recordset({payloads["product_refs"]}::jsonb)
    AS row(
        id uuid, product_id uuid, source_system text, external_product_id text,
        source_checksum varchar(64)
    );

CREATE TEMP TABLE _fixture_variants (
    id uuid PRIMARY KEY,
    product_id uuid NOT NULL,
    variant_code text NOT NULL,
    sku text,
    color text,
    size text,
    status text NOT NULL,
    is_default boolean NOT NULL
) ON COMMIT DROP;
INSERT INTO _fixture_variants
SELECT * FROM jsonb_to_recordset({payloads["variants"]}::jsonb)
    AS row(
        id uuid, product_id uuid, variant_code text, sku text, color text, size text,
        status text, is_default boolean
    );

CREATE TEMP TABLE _fixture_listings (
    id uuid PRIMARY KEY,
    variant_id uuid NOT NULL,
    price numeric(12, 2),
    currency varchar(3),
    availability text NOT NULL,
    status text NOT NULL
) ON COMMIT DROP;
INSERT INTO _fixture_listings
SELECT * FROM jsonb_to_recordset({payloads["listings"]}::jsonb)
    AS row(
        id uuid, variant_id uuid, price numeric(12, 2), currency varchar(3),
        availability text, status text
    );

CREATE TEMP TABLE _fixture_images (
    id uuid PRIMARY KEY,
    product_id uuid NOT NULL,
    variant_id uuid,
    storage_key text NOT NULL,
    mime_type text NOT NULL,
    width integer NOT NULL,
    height integer NOT NULL,
    sha256 varchar(64) NOT NULL,
    sort_order integer NOT NULL,
    is_primary boolean NOT NULL,
    status text NOT NULL
) ON COMMIT DROP;
INSERT INTO _fixture_images
SELECT * FROM jsonb_to_recordset({payloads["images"]}::jsonb)
    AS row(
        id uuid, product_id uuid, variant_id uuid, storage_key text, mime_type text,
        width integer, height integer, sha256 varchar(64), sort_order integer,
        is_primary boolean, status text
    );

CREATE TEMP TABLE _fixture_image_refs (
    id uuid PRIMARY KEY,
    image_id uuid NOT NULL,
    source_system text NOT NULL,
    external_image_id text NOT NULL,
    source_path text NOT NULL
) ON COMMIT DROP;
INSERT INTO _fixture_image_refs
SELECT * FROM jsonb_to_recordset({payloads["image_refs"]}::jsonb)
    AS row(
        id uuid, image_id uuid, source_system text, external_image_id text, source_path text
    );

CREATE TEMP VIEW _fixture_current_state AS
SELECT jsonb_build_object(
    'vendors', (SELECT count(*) FROM catalog.vendors AS vendor
                JOIN _fixture_vendor AS expected ON expected.id = vendor.id),
    'products', (SELECT count(*) FROM catalog.product_external_refs AS ref
                 JOIN _fixture_product_refs AS expected
                   ON expected.source_system = ref.source_system
                  AND expected.external_product_id = ref.external_product_id),
    'product_external_refs', (SELECT count(*) FROM catalog.product_external_refs AS ref
                              JOIN _fixture_product_refs AS expected
                                ON expected.id = ref.id),
    'variants', (SELECT count(*) FROM catalog.product_variants AS variant
                 JOIN _fixture_variants AS expected ON expected.id = variant.id),
    'listings', (SELECT count(*) FROM catalog.listings AS listing
                 JOIN _fixture_listings AS expected ON expected.id = listing.id),
    'images', (SELECT count(*) FROM catalog.product_images AS image
               JOIN _fixture_images AS expected ON expected.id = image.id),
    'image_external_refs', (SELECT count(*) FROM catalog.image_external_refs AS ref
                            JOIN _fixture_image_refs AS expected ON expected.id = ref.id),
    'inventory', (SELECT count(*) FROM inventory.inventory_balances AS balance
                  JOIN _fixture_listings AS expected ON expected.id = balance.listing_id),
    'outbox_events', (SELECT count(*) FROM integration.outbox_events)
) AS value;

CREATE TEMP TABLE _fixture_states (phase text PRIMARY KEY, value jsonb NOT NULL) ON COMMIT DROP;
INSERT INTO _fixture_states SELECT 'start', value FROM _fixture_current_state;

CREATE TEMP TABLE _fixture_assertions (
    check_name text PRIMARY KEY,
    passed boolean NOT NULL CHECK (passed)
) ON COMMIT DROP;

INSERT INTO _fixture_assertions
SELECT 'vendor_state', NOT (
    EXISTS (
        SELECT 1 FROM catalog.vendors AS actual
        JOIN _fixture_vendor AS expected ON expected.id = actual.id
        WHERE ROW(actual.display_name, actual.legal_name, actual.slug, actual.status,
                  actual.created_by_user_id, actual.archived_at)
              IS DISTINCT FROM
              ROW(expected.display_name, NULL::text, expected.slug, 'active'::text,
                  NULL::uuid, NULL::timestamptz)
    ) OR EXISTS (
        SELECT 1 FROM catalog.vendors AS actual
        JOIN _fixture_vendor AS expected ON expected.slug = actual.slug
        WHERE actual.id <> expected.id
    )
);

INSERT INTO _fixture_assertions
SELECT 'product_state', NOT EXISTS (
        SELECT 1 FROM catalog.products AS actual
        JOIN _fixture_products AS expected ON expected.id = actual.id
        WHERE ROW(actual.vendor_id, actual.category_id, actual.name, actual.description,
                  actual.brand_name, actual.status, actual.published_at, actual.created_by_user_id,
                  actual.updated_by_user_id, actual.archived_at)
              IS DISTINCT FROM
              ROW(expected.vendor_id, expected.category_id, expected.name, expected.description,
                  expected.brand_name, expected.status, NULL::timestamptz, NULL::uuid,
                  NULL::uuid, NULL::timestamptz)
);

INSERT INTO _fixture_assertions
SELECT 'product_lineage', NOT (
    EXISTS (
        SELECT 1 FROM catalog.product_external_refs AS actual
        JOIN _fixture_product_refs AS expected
          ON expected.source_system = actual.source_system
         AND expected.external_product_id = actual.external_product_id
        WHERE ROW(actual.id, actual.product_id, actual.source_checksum)
              IS DISTINCT FROM ROW(expected.id, expected.product_id, expected.source_checksum)
    ) OR EXISTS (
        SELECT 1 FROM catalog.product_external_refs AS actual
        WHERE actual.source_system = (SELECT source_system FROM _fixture_vendor)
          AND NOT EXISTS (
              SELECT 1 FROM _fixture_product_refs AS expected
              WHERE expected.source_system = actual.source_system
                AND expected.external_product_id = actual.external_product_id
          )
    )
);

INSERT INTO _fixture_assertions
SELECT 'variant_state', NOT (
    EXISTS (
        SELECT 1 FROM catalog.product_variants AS actual
        JOIN _fixture_variants AS expected ON expected.id = actual.id
        WHERE ROW(actual.product_id, actual.variant_code, actual.sku, actual.color, actual.size,
                  actual.status, actual.is_default, actual.archived_at)
              IS DISTINCT FROM
              ROW(expected.product_id, expected.variant_code, expected.sku, expected.color,
                  expected.size, expected.status, expected.is_default, NULL::timestamptz)
    ) OR EXISTS (
        SELECT 1 FROM catalog.product_variants AS actual
        JOIN _fixture_products AS product ON product.id = actual.product_id
        WHERE NOT EXISTS (SELECT 1 FROM _fixture_variants AS expected WHERE expected.id = actual.id)
    )
);

INSERT INTO _fixture_assertions
SELECT 'listing_state', NOT (
    EXISTS (
        SELECT 1 FROM catalog.listings AS actual
        JOIN _fixture_listings AS expected ON expected.id = actual.id
        WHERE ROW(actual.variant_id, actual.price, actual.currency, actual.availability,
                  actual.status, actual.archived_at)
              IS DISTINCT FROM
              ROW(expected.variant_id, expected.price, expected.currency, expected.availability,
                  expected.status, NULL::timestamptz)
    ) OR EXISTS (
        SELECT 1 FROM catalog.listings AS actual
        JOIN _fixture_variants AS variant ON variant.id = actual.variant_id
        WHERE NOT EXISTS (SELECT 1 FROM _fixture_listings AS expected WHERE expected.id = actual.id)
    )
);

INSERT INTO _fixture_assertions
SELECT 'inventory_absent', NOT EXISTS (
        SELECT 1 FROM inventory.inventory_balances AS actual
        JOIN _fixture_listings AS listing ON listing.id = actual.listing_id
);

INSERT INTO _fixture_assertions
SELECT 'image_state', NOT (
    EXISTS (
        SELECT 1 FROM catalog.product_images AS actual
        JOIN _fixture_images AS expected ON expected.id = actual.id
        WHERE ROW(actual.product_id, actual.variant_id, actual.storage_key, actual.source_url,
                  actual.mime_type, actual.width, actual.height, actual.sha256, actual.sort_order,
                  actual.is_primary, actual.status, actual.archived_at)
              IS DISTINCT FROM
              ROW(expected.product_id, expected.variant_id, expected.storage_key, NULL::text,
                  expected.mime_type, expected.width, expected.height, expected.sha256,
                  expected.sort_order, expected.is_primary, expected.status, NULL::timestamptz)
    ) OR EXISTS (
        SELECT 1 FROM catalog.product_images AS actual
        JOIN _fixture_products AS product ON product.id = actual.product_id
        WHERE NOT EXISTS (SELECT 1 FROM _fixture_images AS expected WHERE expected.id = actual.id)
    )
);

INSERT INTO _fixture_assertions
SELECT 'image_lineage', NOT (
    EXISTS (
        SELECT 1 FROM catalog.image_external_refs AS actual
        JOIN _fixture_image_refs AS expected
          ON expected.source_system = actual.source_system
         AND expected.external_image_id = actual.external_image_id
        WHERE ROW(actual.id, actual.image_id, actual.source_path)
              IS DISTINCT FROM ROW(expected.id, expected.image_id, expected.source_path)
    ) OR EXISTS (
        SELECT 1 FROM catalog.image_external_refs AS actual
        WHERE actual.source_system = (SELECT source_system FROM _fixture_vendor)
          AND NOT EXISTS (
              SELECT 1 FROM _fixture_image_refs AS expected
              WHERE expected.source_system = actual.source_system
                AND expected.external_image_id = actual.external_image_id
          )
    )
);

CREATE TEMP TABLE _fixture_created (entity text PRIMARY KEY, count bigint NOT NULL) ON COMMIT DROP;

WITH inserted AS (
    INSERT INTO catalog.vendors (id, display_name, slug, status)
    SELECT id, display_name, slug, 'active' FROM _fixture_vendor
    ON CONFLICT (id) DO NOTHING RETURNING 1
)
INSERT INTO _fixture_created SELECT 'vendors', count(*) FROM inserted;

WITH inserted AS (
    INSERT INTO catalog.products (
        id, vendor_id, category_id, name, description, brand_name, status
    )
    SELECT id, vendor_id, category_id, name, description, brand_name, status
    FROM _fixture_products
    ON CONFLICT (id) DO NOTHING RETURNING 1
)
INSERT INTO _fixture_created SELECT 'products', count(*) FROM inserted;

WITH inserted AS (
    INSERT INTO catalog.product_external_refs (
        id, product_id, source_system, external_product_id, source_checksum
    )
    SELECT id, product_id, source_system, external_product_id, source_checksum
    FROM _fixture_product_refs
    ON CONFLICT (id) DO NOTHING RETURNING 1
)
INSERT INTO _fixture_created SELECT 'product_external_refs', count(*) FROM inserted;

WITH inserted AS (
    INSERT INTO catalog.product_variants (
        id, product_id, variant_code, sku, color, size, status, is_default
    )
    SELECT id, product_id, variant_code, sku, color, size, status, is_default
    FROM _fixture_variants
    ON CONFLICT (id) DO NOTHING RETURNING 1
)
INSERT INTO _fixture_created SELECT 'variants', count(*) FROM inserted;

WITH inserted AS (
    INSERT INTO catalog.listings (
        id, variant_id, price, currency, availability, status
    )
    SELECT id, variant_id, price, currency, availability, status
    FROM _fixture_listings
    ON CONFLICT (id) DO NOTHING RETURNING 1
)
INSERT INTO _fixture_created SELECT 'listings', count(*) FROM inserted;

WITH inserted AS (
    INSERT INTO catalog.product_images (
        id, product_id, variant_id, storage_key, mime_type, width, height, sha256,
        sort_order, is_primary, status
    )
    SELECT id, product_id, variant_id, storage_key, mime_type, width, height, sha256,
           sort_order, is_primary, status
    FROM _fixture_images
    ON CONFLICT (id) DO NOTHING RETURNING 1
)
INSERT INTO _fixture_created SELECT 'images', count(*) FROM inserted;

WITH inserted AS (
    INSERT INTO catalog.image_external_refs (
        id, image_id, source_system, external_image_id, source_path
    )
    SELECT id, image_id, source_system, external_image_id, source_path
    FROM _fixture_image_refs
    ON CONFLICT (id) DO NOTHING RETURNING 1
)
INSERT INTO _fixture_created SELECT 'image_external_refs', count(*) FROM inserted;

INSERT INTO _fixture_created VALUES ('inventory', 0), ('outbox_events', 0);
INSERT INTO _fixture_states SELECT 'end', value FROM _fixture_current_state;

SELECT '{IMPORT_RESULT_MARKER}' || jsonb_build_object(
    'start_state', (SELECT value FROM _fixture_states WHERE phase = 'start'),
    'created', (SELECT jsonb_object_agg(entity, count ORDER BY entity) FROM _fixture_created),
    'end_state', (SELECT value FROM _fixture_states WHERE phase = 'end')
)::text;
COMMIT;
"""


def import_canonical_batch(config: DatabaseConfig, batch: CanonicalImportBatch) -> ImportExecution:
    try:
        completed = run_psql(config, stdin_sql=_import_sql(batch))
    except Exception as error:
        stderr = getattr(error, "stderr", "") or ""
        detail = stderr.strip().splitlines()[-1] if stderr.strip() else "PostgreSQL rejected input"
        raise CanonicalImportError(
            f"Canonical fixture transaction failed and was rolled back: {detail}"
        ) from error
    result_line = next(
        (line for line in completed.stdout.splitlines() if line.startswith(IMPORT_RESULT_MARKER)),
        None,
    )
    if result_line is None:
        raise CanonicalImportError("Importer did not return a transaction result")
    payload = json.loads(result_line.removeprefix(IMPORT_RESULT_MARKER))
    return ImportExecution(
        start_state={key: int(value) for key, value in payload["start_state"].items()},
        created={key: int(value) for key, value in payload["created"].items()},
        end_state={key: int(value) for key, value in payload["end_state"].items()},
    )


def verify_batch_parity(config: DatabaseConfig, batch: CanonicalImportBatch) -> dict[str, Any]:
    source = batch.external_source.replace("'", "''")
    actual_rows = query_json(
        config,
        f"""
        SELECT COALESCE(jsonb_agg(to_jsonb(q) ORDER BY external_product_id, variant_code),
                              '[]'::jsonb)
        FROM (
            SELECT
                ref.source_system AS external_source,
                ref.external_product_id,
                product.name,
                product.description,
                product.brand_name,
                product.category_id::text AS category_id,
                product.status AS product_status,
                variant.variant_code,
                variant.color,
                variant.size,
                variant.sku,
                variant.is_default,
                variant.status AS variant_status,
                listing.price::text AS price,
                listing.currency,
                listing.availability,
                listing.status AS listing_status,
                balance.on_hand_quantity,
                balance.listing_id IS NOT NULL AS inventory_row_exists
            FROM catalog.product_external_refs AS ref
            JOIN catalog.products AS product ON product.id = ref.product_id
            JOIN catalog.product_variants AS variant ON variant.product_id = product.id
            JOIN catalog.listings AS listing ON listing.variant_id = variant.id
            LEFT JOIN inventory.inventory_balances AS balance ON balance.listing_id = listing.id
            WHERE ref.source_system = '{source}'
        ) AS q;
        """,
    )
    actual_by_product: dict[str, dict[str, Any]] = {}
    for row in actual_rows:
        product_entry = actual_by_product.setdefault(
            row["external_product_id"],
            {
                "external_source": row["external_source"],
                "external_product_id": row["external_product_id"],
                "product": {
                    "name": row["name"],
                    "description": row["description"],
                    "brand_name": row["brand_name"],
                    "category_id": row["category_id"],
                    "status": row["product_status"],
                },
                "variants": [],
            },
        )
        product_entry["variants"].append(
            {
                "variant_code": row["variant_code"],
                "color": row["color"],
                "size": row["size"],
                "sku": row["sku"],
                "is_default": row["is_default"],
                "status": row["variant_status"],
                "listing": {
                    "price": row["price"],
                    "currency": row["currency"],
                    "availability": row["availability"],
                    "status": row["listing_status"],
                },
                "inventory": {"on_hand_quantity": row["on_hand_quantity"]},
            }
        )
    actual_projection = [actual_by_product[key] for key in sorted(actual_by_product)]
    expected_projection = semantic_projection(batch)

    actual_images = query_json(
        config,
        f"""
        SELECT COALESCE(
            jsonb_agg(to_jsonb(q) ORDER BY external_product_id, external_image_id),
            '[]'::jsonb
        )
        FROM (
            SELECT
                product_ref.source_system AS external_source,
                product_ref.external_product_id,
                image_ref.external_image_id,
                image_ref.source_path,
                image.storage_key,
                image.mime_type,
                image.sha256,
                image.width,
                image.height,
                image.sort_order,
                image.is_primary,
                variant.variant_code
            FROM catalog.image_external_refs AS image_ref
            JOIN catalog.product_images AS image ON image.id = image_ref.image_id
            JOIN catalog.product_external_refs AS product_ref
              ON product_ref.product_id = image.product_id
             AND product_ref.source_system = image_ref.source_system
            LEFT JOIN catalog.product_variants AS variant ON variant.id = image.variant_id
            WHERE image_ref.source_system = '{source}'
        ) AS q;
        """,
    )
    expected_images = image_projection(batch)
    actual_semantic_checksum = content_checksum(actual_projection)
    expected_semantic_checksum = semantic_checksum(batch)
    counts = {
        "products": len({row["external_product_id"] for row in actual_rows}),
        "variants": len(actual_rows),
        "listings": len(actual_rows),
        "product_external_refs": len({row["external_product_id"] for row in actual_rows}),
        "images": len(actual_images),
        "image_external_refs": len(actual_images),
        "inventory": sum(bool(row["inventory_row_exists"]) for row in actual_rows),
    }
    expected_counts = {
        "products": len(batch.products),
        "variants": sum(len(product.variants) for product in batch.products),
        "listings": sum(len(product.variants) for product in batch.products),
        "product_external_refs": len(batch.products),
        "images": sum(len(product.images) for product in batch.products),
        "image_external_refs": sum(len(product.images) for product in batch.products),
        "inventory": 0,
    }
    field_checks = {
        "semantic_projection_equal": actual_projection == expected_projection,
        "image_projection_equal": actual_images == expected_images,
        "brand_absent": all(row["brand_name"] is None for row in actual_rows),
        "category_absent": all(row["category_id"] is None for row in actual_rows),
        "size_absent": all(row["size"] is None for row in actual_rows),
        "currency_absent": all(row["currency"] is None for row in actual_rows),
        "inventory_absent": counts["inventory"] == 0,
        "one_default_variant_per_product": all(
            sum(bool(variant["is_default"]) for variant in product["variants"]) == 1
            for product in actual_projection
        ),
        "listings_are_draft": all(row["listing_status"] == "draft" for row in actual_rows),
    }
    forbidden = query_json(
        config,
        """
        SELECT jsonb_build_object(
            'search_schema', to_regnamespace('search') IS NOT NULL,
            'commerce_schema', to_regnamespace('commerce') IS NOT NULL,
            'vector_extension', EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector'),
            'tsvector_columns', EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE udt_name = 'tsvector'
                  AND table_schema NOT IN ('pg_catalog', 'information_schema')
            )
        );
        """,
    )
    checks = {
        "counts_equal": counts == expected_counts,
        "semantic_checksum_equal": actual_semantic_checksum == expected_semantic_checksum,
        "all_field_checks_pass": all(field_checks.values()),
        "forbidden_infrastructure_absent": not any(forbidden.values()),
    }
    result_end_state = {**counts, "vendors": 1, "outbox_events": 0}
    return {
        "status": "GREEN" if all(checks.values()) else "RED",
        "checks": checks,
        "field_checks": field_checks,
        "counts": counts,
        "expected_counts": expected_counts,
        "semantic_checksum": actual_semantic_checksum,
        "expected_semantic_checksum": expected_semantic_checksum,
        "import_result_checksum": import_result_checksum(batch, result_end_state),
        "forbidden_infrastructure": forbidden,
    }
