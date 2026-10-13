"""Explicit backend adapter boundary; external catalogue IDs are never UUID aliases."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from uuid import UUID

from sahulat_visual.domain import ProductMatch


@dataclass(frozen=True)
class ExternalImageReference:
    source_system: str
    external_product_id: str
    external_image_id: str
    product_id: UUID
    image_id: UUID


@dataclass(frozen=True)
class CanonicalMatch:
    product_id: UUID
    matched_image_id: UUID
    score: float
    external_product_id: str
    external_image_id: str


def resolve_canonical_matches(
    source_system: str,
    matches: Sequence[ProductMatch],
    references: Iterable[ExternalImageReference],
) -> tuple[CanonicalMatch, ...]:
    """Resolve an authorized backend-supplied ref projection, without sorting/filtering.

    The backend obtains these identities from product/image external refs joined through
    product_images.product_id. This function never opens the business database or authorizes
    results. Missing/ambiguous lineage fails rather than returning partial rankings.
    """
    by_image: dict[str, ExternalImageReference] = {}
    by_product: dict[str, UUID] = {}
    for ref in references:
        if ref.source_system != source_system:
            raise ValueError("External reference namespace mismatch")
        if not isinstance(ref.product_id, UUID) or not isinstance(ref.image_id, UUID):
            raise ValueError("Canonical identities must be UUIDs")
        if not ref.external_product_id.strip() or not ref.external_image_id.strip():
            raise ValueError("External identities must be present")
        if ref.external_image_id in by_image:
            raise ValueError("Duplicate external image reference")
        previous = by_product.get(ref.external_product_id)
        if previous is not None and previous != ref.product_id:
            raise ValueError("Conflicting canonical product references")
        by_image[ref.external_image_id] = ref
        by_product[ref.external_product_id] = ref.product_id
    resolved = []
    seen_products: set[UUID] = set()
    for match in matches:
        matched_ref = by_image.get(match.matched_image_id)
        if matched_ref is None or matched_ref.external_product_id != match.product_id:
            raise ValueError("Missing or cross-product image lineage")
        if matched_ref.product_id in seen_products:
            raise ValueError("External products resolve to duplicate canonical identity")
        seen_products.add(matched_ref.product_id)
        resolved.append(
            CanonicalMatch(
                matched_ref.product_id,
                matched_ref.image_id,
                match.score,
                match.product_id,
                match.matched_image_id,
            )
        )
    return tuple(resolved)
