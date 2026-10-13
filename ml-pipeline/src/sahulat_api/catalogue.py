"""Optional read-only reference projection for the backend integration boundary.

Not used by HTTP startup or requests. The host supplies its own authorized DB context.
"""

import re
from uuid import UUID

from sahulat_database.migrations import DatabaseConfig, query_json

from .identity import ExternalImageReference


def load_external_image_references(
    config: DatabaseConfig, source_system: str
) -> tuple[ExternalImageReference, ...]:
    if not re.fullmatch(r"[a-z][a-z0-9_-]{1,63}", source_system):
        raise ValueError("Invalid source namespace")
    rows = query_json(
        config,
        f"""
        SELECT COALESCE(jsonb_agg(to_jsonb(ref) ORDER BY external_product_id, external_image_id),
            '[]'::jsonb)
        FROM (
            SELECT image_ref.source_system, product_ref.external_product_id,
                image_ref.external_image_id, image.product_id, image.id AS image_id
            FROM catalog.image_external_refs AS image_ref
            JOIN catalog.product_images AS image ON image.id = image_ref.image_id
            JOIN catalog.product_external_refs AS product_ref
              ON product_ref.product_id = image.product_id
             AND product_ref.source_system = image_ref.source_system
            WHERE image_ref.source_system = '{source_system}'
        ) AS ref;
        """,
    )
    return tuple(
        ExternalImageReference(
            row["source_system"],
            row["external_product_id"],
            row["external_image_id"],
            UUID(row["product_id"]),
            UUID(row["image_id"]),
        )
        for row in rows
    )
