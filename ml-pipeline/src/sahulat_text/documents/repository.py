"""Read-only, snapshot-consistent canonical Product projection; no fixture dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sahulat_database.migrations import DatabaseConfig, query_json

from .projection import CanonicalProductProjection

PROJECTION_SQL = """
WITH product_rows AS (
    SELECT product.id, product.name, product.description, product.status, product.archived_at,
        COALESCE((
            SELECT jsonb_agg(variant.color)
            FROM catalog.product_variants AS variant
            WHERE variant.product_id = product.id
              AND variant.archived_at IS NULL AND variant.status <> 'archived'
              AND variant.color IS NOT NULL
        ), '[]'::jsonb) AS colors
    FROM catalog.products AS product
)
SELECT jsonb_build_object(
    'products', COALESCE((SELECT jsonb_agg(jsonb_build_object(
        'product_id', id, 'name', name, 'description', description, 'colors', colors
    ) ORDER BY id) FROM product_rows
        WHERE archived_at IS NULL AND status <> 'archived'), '[]'::jsonb),
    'excluded_product_ids', COALESCE((SELECT jsonb_agg(id ORDER BY id) FROM product_rows
        WHERE archived_at IS NOT NULL OR status = 'archived'), '[]'::jsonb),
    'products_read', (SELECT count(*) FROM product_rows),
    'migrations', COALESCE((SELECT jsonb_agg(jsonb_build_object(
        'migration_id', migration_id, 'checksum', checksum
    ) ORDER BY migration_id) FROM integration.schema_migrations), '[]'::jsonb)
);
"""


@dataclass(frozen=True, slots=True)
class ProductProjectionSnapshot:
    projections: tuple[CanonicalProductProjection, ...]
    excluded_product_ids: tuple[UUID, ...]
    products_read: int
    migrations: tuple[tuple[str, str], ...]


def load_product_projection_snapshot(config: DatabaseConfig) -> ProductProjectionSnapshot:
    data: dict[str, Any] = query_json(config, PROJECTION_SQL)
    return ProductProjectionSnapshot(
        projections=tuple(
            CanonicalProductProjection(
                UUID(row["product_id"]), row["name"], row["description"], tuple(row["colors"])
            )
            for row in data["products"]
        ),
        excluded_product_ids=tuple(UUID(value) for value in data["excluded_product_ids"]),
        products_read=data["products_read"],
        migrations=tuple((row["migration_id"], row["checksum"]) for row in data["migrations"]),
    )


def load_product_projections(config: DatabaseConfig) -> tuple[CanonicalProductProjection, ...]:
    return load_product_projection_snapshot(config).projections
