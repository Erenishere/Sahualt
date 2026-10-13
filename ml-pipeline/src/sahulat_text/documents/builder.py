from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sahulat_text.normalization import normalize_text, require_document_unicode_version

from .projection import CanonicalProductProjection, DocumentContractError
from .serialization import canonical_json_bytes, sha256

SCHEMA_VERSION = "product-text-v1"
BUILDER_VERSION = "product-text-builder-v1"
SORT_POLICY = "canonical lowercase hyphenated product UUID ascending (Unicode code-point order)"


@dataclass(frozen=True, slots=True)
class ProductTextDocument:
    product_id: UUID
    name: str
    description: str
    colors: tuple[str, ...]
    text: str
    document_checksum: str

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "product_id": str(self.product_id),
            "fields": {
                "name": self.name,
                "description": self.description,
                "colors": list(self.colors),
            },
            "text": self.text,
        }

    def record(self) -> dict[str, Any]:
        return {**self.payload(), "document_checksum": self.document_checksum}


def build_product_document(projection: CanonicalProductProjection) -> ProductTextDocument:
    require_document_unicode_version()
    name = normalize_text(projection.name)
    description = normalize_text(projection.description)
    if not name or not description:
        raise DocumentContractError(f"invalid required semantic fields for {projection.product_id}")
    colors = tuple(
        sorted({normalized for color in projection.colors if (normalized := normalize_text(color))})
    )
    text = f"Product Name: {name}\nDescription: {description}"
    if colors:
        text += f"\nColor: {', '.join(colors)}"
    document = ProductTextDocument(projection.product_id, name, description, colors, text, "")
    try:
        checksum = sha256(canonical_json_bytes(document.payload()))
    except UnicodeEncodeError as error:
        raise DocumentContractError(f"invalid Unicode for {projection.product_id}") from error
    return ProductTextDocument(projection.product_id, name, description, colors, text, checksum)


def build_product_documents(
    projections: Iterable[CanonicalProductProjection],
) -> list[ProductTextDocument]:
    require_document_unicode_version()
    documents = [build_product_document(projection) for projection in projections]
    identities = [document.product_id for document in documents]
    if len(identities) != len(set(identities)):
        raise DocumentContractError("duplicate canonical product identity in document batch")
    return sorted(documents, key=lambda document: str(document.product_id))


def serialize_documents(documents: Iterable[ProductTextDocument]) -> bytes:
    ordered = sorted(documents, key=lambda document: str(document.product_id))
    identities = [document.product_id for document in ordered]
    if len(identities) != len(set(identities)):
        raise DocumentContractError("duplicate document identity in artifact")
    for document in ordered:
        if sha256(canonical_json_bytes(document.payload())) != document.document_checksum:
            raise DocumentContractError("document checksum mismatch")
    return b"".join(canonical_json_bytes(document.record()) + b"\n" for document in ordered)
