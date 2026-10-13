"""Canonical product-ingestion contracts; independent of retrieval documents."""

from .canonical import semantic_checksum
from .contracts import (
    CanonicalImageInput,
    CanonicalImportBatch,
    CanonicalListingInput,
    CanonicalProductInput,
    CanonicalVariantInput,
)

__all__ = [
    "CanonicalImageInput",
    "CanonicalImportBatch",
    "CanonicalListingInput",
    "CanonicalProductInput",
    "CanonicalVariantInput",
    "semantic_checksum",
]
