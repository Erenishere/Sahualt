from __future__ import annotations

import hashlib
import json
import uuid
from decimal import Decimal
from typing import Any

from .contracts import CanonicalImportBatch, CanonicalProductInput

FIXTURE_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL, "https://sahulat.ai/namespaces/fixture-ingestion-v1"
)


def content_checksum(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def fixture_uuid(external_source: str, entity: str, identity: str) -> uuid.UUID:
    return uuid.uuid5(FIXTURE_NAMESPACE, f"{external_source}:{entity}:{identity}")


def vendor_uuid(external_source: str) -> uuid.UUID:
    return fixture_uuid(external_source, "vendor", external_source)


def product_uuid(product: CanonicalProductInput) -> uuid.UUID:
    return fixture_uuid(product.external_source, "product", product.external_product_id)


def variant_uuid(product: CanonicalProductInput, variant_code: str) -> uuid.UUID:
    return fixture_uuid(
        product.external_source,
        "variant",
        f"{product.external_product_id}:{variant_code}",
    )


def listing_uuid(product: CanonicalProductInput, variant_code: str) -> uuid.UUID:
    return fixture_uuid(
        product.external_source,
        "listing",
        f"{product.external_product_id}:{variant_code}",
    )


def product_external_ref_uuid(product: CanonicalProductInput) -> uuid.UUID:
    return fixture_uuid(
        product.external_source, "product-external-ref", product.external_product_id
    )


def image_uuid(product: CanonicalProductInput, external_image_id: str) -> uuid.UUID:
    return fixture_uuid(product.external_source, "image", external_image_id)


def image_external_ref_uuid(product: CanonicalProductInput, external_image_id: str) -> uuid.UUID:
    return fixture_uuid(product.external_source, "image-external-ref", external_image_id)


def decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else format(value.quantize(Decimal("0.01")), ".2f")


def semantic_projection(batch: CanonicalImportBatch) -> list[dict[str, Any]]:
    projection: list[dict[str, Any]] = []
    for product in sorted(batch.products, key=lambda item: item.external_product_id):
        projection.append(
            {
                "external_source": product.external_source,
                "external_product_id": product.external_product_id,
                "product": {
                    "name": product.name,
                    "description": product.description,
                    "brand_name": product.brand_name,
                    "category_id": str(product.category_id) if product.category_id else None,
                    "status": product.status,
                },
                "variants": [
                    {
                        "variant_code": variant.variant_code,
                        "color": variant.color,
                        "size": variant.size,
                        "sku": variant.sku,
                        "is_default": variant.is_default,
                        "status": variant.status,
                        "listing": {
                            "price": decimal_text(variant.listing.price),
                            "currency": variant.listing.currency,
                            "availability": variant.listing.availability,
                            "status": variant.listing.status,
                        },
                        "inventory": {"on_hand_quantity": None},
                    }
                    for variant in sorted(product.variants, key=lambda item: item.variant_code)
                ],
            }
        )
    return projection


def image_projection(batch: CanonicalImportBatch) -> list[dict[str, Any]]:
    return [
        {
            "external_source": product.external_source,
            "external_product_id": product.external_product_id,
            "external_image_id": image.external_image_id,
            "source_path": image.source_path,
            "storage_key": image.storage_key,
            "mime_type": image.mime_type,
            "sha256": image.sha256,
            "width": image.width,
            "height": image.height,
            "sort_order": image.sort_order,
            "is_primary": image.is_primary,
            "variant_code": image.variant_code,
        }
        for product in sorted(batch.products, key=lambda item: item.external_product_id)
        for image in sorted(product.images, key=lambda item: item.external_image_id)
    ]


def semantic_checksum(batch: CanonicalImportBatch) -> str:
    return content_checksum(semantic_projection(batch))


def import_result_checksum(batch: CanonicalImportBatch, end_state: dict[str, int]) -> str:
    return content_checksum(
        {
            "semantic_checksum": semantic_checksum(batch),
            "images": image_projection(batch),
            "end_state": dict(sorted(end_state.items())),
        }
    )
