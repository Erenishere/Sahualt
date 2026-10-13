from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath
from typing import Any

from ..canonical import content_checksum
from ..contracts import (
    CanonicalImageInput,
    CanonicalImportBatch,
    CanonicalListingInput,
    CanonicalProductInput,
    CanonicalVariantInput,
    IngestionContractError,
    normalize_ingestion_text,
)
from .reader import EXPECTED_SOURCE_SYSTEM, KhaadiAuthority

IMPORTER_VERSION = "fixture-ingestion-v1"
FIXTURE_VENDOR_NAME = "Khaadi Evaluation Fixture"
FIXTURE_VENDOR_SLUG = "fixture-khaadi-v1"
AVAILABILITY_MAPPING = {"In Stock": "in_stock"}
IMAGE_MIME_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


class KhaadiMappingError(ValueError):
    """Raised when audited Khaadi data cannot map to DB-CONTRACT-V1."""


@dataclass(frozen=True, slots=True)
class KhaadiMappingResult:
    batch: CanonicalImportBatch
    source_products: int
    importable_product_ids: tuple[str, ...]
    quarantined_products: tuple[dict[str, Any], ...]
    rejected_products: tuple[dict[str, Any], ...]
    raw_images: int
    retained_images: int
    excluded_images: tuple[dict[str, Any], ...]


def _mime_type(image_path: str) -> str:
    suffix = PurePosixPath(image_path).suffix.lower()
    try:
        return IMAGE_MIME_TYPES[suffix]
    except KeyError as error:
        raise KhaadiMappingError(f"Unsupported retained image type: {suffix}") from error


def _row_checksum(row: dict[str, str]) -> str:
    return content_checksum(dict(sorted(row.items())))


def _map_product(row: dict[str, str], images: tuple[dict[str, Any], ...]) -> CanonicalProductInput:
    external_product_id = normalize_ingestion_text(row["ID"])
    name = normalize_ingestion_text(row["Product Name"])
    description = normalize_ingestion_text(row["Product Description"])
    color = normalize_ingestion_text(row["Color"]) or None
    raw_availability = normalize_ingestion_text(row["Availability"])
    if raw_availability not in AVAILABILITY_MAPPING:
        raise KhaadiMappingError(
            f"Availability value has no Fixture Ingestion V1 mapping: {raw_availability!r}"
        )
    try:
        price = Decimal(normalize_ingestion_text(row["Price"]))
    except InvalidOperation as error:
        raise KhaadiMappingError("Price is not a deterministic decimal") from error

    mapped_images = tuple(
        CanonicalImageInput(
            external_image_id=image["image_id"],
            storage_key=f"fixtures/{EXPECTED_SOURCE_SYSTEM}/{image['image_id']}",
            source_path=image["image_path"],
            mime_type=_mime_type(image["image_path"]),
            sha256=image["binary_sha256"],
            width=int(image["width"]),
            height=int(image["height"]),
            sort_order=position,
            is_primary=position == 0,
            variant_code=None,
        )
        for position, image in enumerate(sorted(images, key=lambda item: item["image_id"]))
    )
    return CanonicalProductInput(
        external_source=EXPECTED_SOURCE_SYSTEM,
        external_product_id=external_product_id,
        source_checksum=_row_checksum(row),
        name=name,
        description=description,
        brand_name=None,
        category_id=None,
        status="draft",
        variants=(
            CanonicalVariantInput(
                variant_code="default",
                color=color,
                size=None,
                sku=None,
                status="draft",
                is_default=True,
                listing=CanonicalListingInput(
                    price=price,
                    currency=None,
                    availability=AVAILABILITY_MAPPING[raw_availability],
                    status="draft",
                ),
            ),
        ),
        images=mapped_images,
    )


def map_khaadi_fixture(authority: KhaadiAuthority) -> KhaadiMappingResult:
    images_by_product: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for image in authority.visual_retained:
        images_by_product[image["product_id"]].append(image)

    quarantined_ids = {
        item["product_id"]
        for item in authority.quarantined_products
        if isinstance(item.get("product_id"), str)
    }
    products: list[CanonicalProductInput] = []
    rejected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for position, row in enumerate(authority.rows, start=1):
        product_id = normalize_ingestion_text(row.get("ID", ""))
        if not product_id:
            rejected.append(
                {"source_position": position, "product_id": None, "reason": "missing-id"}
            )
            continue
        if product_id in quarantined_ids:
            continue
        if product_id not in authority.valid_product_ids:
            rejected.append(
                {
                    "source_position": position,
                    "product_id": product_id,
                    "reason": "not-approved-by-gate-1",
                }
            )
            continue
        if product_id in seen_ids:
            rejected.append(
                {
                    "source_position": position,
                    "product_id": product_id,
                    "reason": "duplicate-importable-id",
                }
            )
            continue
        seen_ids.add(product_id)
        try:
            products.append(_map_product(row, tuple(images_by_product[product_id])))
        except (IngestionContractError, KhaadiMappingError) as error:
            rejected.append(
                {
                    "source_position": position,
                    "product_id": product_id,
                    "reason": str(error),
                }
            )

    expected_ids = set(authority.valid_product_ids)
    mapped_ids = {product.external_product_id for product in products}
    if mapped_ids != expected_ids or rejected:
        raise KhaadiMappingError(
            "Audited importable products no longer map cleanly; rerun Gate 1 before importing"
        )

    products.sort(key=lambda product: product.external_product_id)
    batch = CanonicalImportBatch(
        importer_version=IMPORTER_VERSION,
        external_source=EXPECTED_SOURCE_SYSTEM,
        vendor_display_name=FIXTURE_VENDOR_NAME,
        vendor_slug=FIXTURE_VENDOR_SLUG,
        products=tuple(products),
    )
    return KhaadiMappingResult(
        batch=batch,
        source_products=len(authority.rows),
        importable_product_ids=tuple(sorted(mapped_ids)),
        quarantined_products=authority.quarantined_products,
        rejected_products=tuple(rejected),
        raw_images=len(authority.visual_retained) + len(authority.visual_excluded),
        retained_images=len(authority.visual_retained),
        excluded_images=authority.visual_excluded,
    )
