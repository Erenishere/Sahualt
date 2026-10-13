"""Canonical product-text-v1 construction and validation boundary."""

from .builder import ProductTextDocument, build_product_document, build_product_documents
from .projection import CanonicalProductProjection, DocumentContractError

__all__ = [
    "CanonicalProductProjection",
    "DocumentContractError",
    "ProductTextDocument",
    "build_product_document",
    "build_product_documents",
]
