from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sahulat_text.normalization import normalize_text as normalize_ingestion_text

SHA256 = re.compile(r"^[0-9a-f]{64}$")
SOURCE_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
LISTING_AVAILABILITY = frozenset({"unknown", "in_stock", "out_of_stock", "preorder", "unavailable"})
LISTING_STATUSES = frozenset({"draft", "active", "paused", "archived"})
PRODUCT_STATUSES = frozenset({"draft", "published", "paused", "archived"})
VARIANT_STATUSES = frozenset({"draft", "active", "paused", "archived"})


class IngestionContractError(ValueError):
    """Raised when canonical ingestion input violates DB-CONTRACT-V1."""


def _required_text(name: str, value: str) -> None:
    if not isinstance(value, str) or not value:
        raise IngestionContractError(f"{name} must be a non-empty string")
    if value != normalize_ingestion_text(value):
        raise IngestionContractError(f"{name} must already use canonical normalization")


def _optional_text(name: str, value: str | None) -> None:
    if value is not None:
        _required_text(name, value)


@dataclass(frozen=True, slots=True)
class CanonicalListingInput:
    price: Decimal | None
    currency: str | None
    availability: str
    status: str = "draft"

    def __post_init__(self) -> None:
        if self.price is not None:
            if not self.price.is_finite() or self.price < 0:
                raise IngestionContractError("price must be a finite non-negative decimal")
            if self.price != self.price.quantize(Decimal("0.01")):
                raise IngestionContractError("price may have at most two decimal places")
            if self.price > Decimal("9999999999.99"):
                raise IngestionContractError("price exceeds NUMERIC(12,2)")
        if self.currency is not None and not re.fullmatch(r"[A-Z]{3}", self.currency):
            raise IngestionContractError("currency must be an uppercase three-letter code")
        if self.availability not in LISTING_AVAILABILITY:
            raise IngestionContractError("availability is outside DB-CONTRACT-V1")
        if self.status not in LISTING_STATUSES:
            raise IngestionContractError("listing status is outside DB-CONTRACT-V1")
        if self.status == "active" and (
            self.price is None or self.currency is None or self.availability == "unknown"
        ):
            raise IngestionContractError(
                "active listing requires price, currency, and availability"
            )


@dataclass(frozen=True, slots=True)
class CanonicalVariantInput:
    variant_code: str
    color: str | None
    size: str | None
    is_default: bool
    listing: CanonicalListingInput
    sku: str | None = None
    status: str = "draft"

    def __post_init__(self) -> None:
        _required_text("variant_code", self.variant_code)
        _optional_text("color", self.color)
        _optional_text("size", self.size)
        _optional_text("sku", self.sku)
        if self.status not in VARIANT_STATUSES:
            raise IngestionContractError("variant status is outside DB-CONTRACT-V1")


@dataclass(frozen=True, slots=True)
class CanonicalImageInput:
    external_image_id: str
    storage_key: str
    source_path: str
    mime_type: str
    sha256: str
    width: int
    height: int
    sort_order: int
    is_primary: bool
    variant_code: str | None = None

    def __post_init__(self) -> None:
        _required_text("external_image_id", self.external_image_id)
        _required_text("storage_key", self.storage_key)
        _required_text("source_path", self.source_path)
        _required_text("mime_type", self.mime_type)
        _optional_text("variant_code", self.variant_code)
        if not SHA256.fullmatch(self.sha256):
            raise IngestionContractError("image sha256 must be lowercase hexadecimal")
        if self.width <= 0 or self.height <= 0:
            raise IngestionContractError("image dimensions must be positive")
        if self.sort_order < 0:
            raise IngestionContractError("image sort_order must be non-negative")
        if self.source_path.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", self.source_path):
            raise IngestionContractError("source_path must be repository-portable")


@dataclass(frozen=True, slots=True)
class CanonicalProductInput:
    external_source: str
    external_product_id: str
    source_checksum: str
    name: str
    description: str
    variants: tuple[CanonicalVariantInput, ...]
    images: tuple[CanonicalImageInput, ...] = ()
    brand_name: str | None = None
    category_id: UUID | None = None
    status: str = "draft"

    def __post_init__(self) -> None:
        if not SOURCE_NAME.fullmatch(self.external_source):
            raise IngestionContractError("external_source must be a normalized source namespace")
        _required_text("external_product_id", self.external_product_id)
        if not SHA256.fullmatch(self.source_checksum):
            raise IngestionContractError("source_checksum must be lowercase hexadecimal")
        _required_text("name", self.name)
        _required_text("description", self.description)
        _optional_text("brand_name", self.brand_name)
        if self.status not in PRODUCT_STATUSES:
            raise IngestionContractError("product status is outside DB-CONTRACT-V1")
        if not self.variants:
            raise IngestionContractError("a product must have at least one variant")
        variant_codes = [variant.variant_code for variant in self.variants]
        if len(variant_codes) != len(set(variant_codes)):
            raise IngestionContractError("variant_code values must be unique per product")
        if sum(variant.is_default for variant in self.variants) != 1:
            raise IngestionContractError("a product must have exactly one default variant")
        known_codes = set(variant_codes)
        image_ids = [image.external_image_id for image in self.images]
        if len(image_ids) != len(set(image_ids)):
            raise IngestionContractError("external image IDs must be unique per product")
        if any(
            image.variant_code is not None and image.variant_code not in known_codes
            for image in self.images
        ):
            raise IngestionContractError("image variant_code must identify a product variant")


@dataclass(frozen=True, slots=True)
class CanonicalImportBatch:
    importer_version: str
    external_source: str
    vendor_display_name: str
    vendor_slug: str
    products: tuple[CanonicalProductInput, ...]

    def __post_init__(self) -> None:
        _required_text("importer_version", self.importer_version)
        if not SOURCE_NAME.fullmatch(self.external_source):
            raise IngestionContractError("external_source must be a normalized source namespace")
        _required_text("vendor_display_name", self.vendor_display_name)
        if not SOURCE_NAME.fullmatch(self.vendor_slug):
            raise IngestionContractError("vendor_slug must be a normalized slug")
        external_ids = [product.external_product_id for product in self.products]
        if len(external_ids) != len(set(external_ids)):
            raise IngestionContractError("external product IDs must be unique in an import batch")
        if any(product.external_source != self.external_source for product in self.products):
            raise IngestionContractError("every product must use the batch external_source")
