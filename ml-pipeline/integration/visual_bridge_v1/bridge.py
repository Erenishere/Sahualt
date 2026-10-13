from typing import Protocol

from .client import VisualAIClient
from .errors import BridgeError
from .models import ResolvedVisualMatch, VisualSearch


class CatalogueReader(Protocol):
    async def resolve(self, search: VisualSearch) -> tuple[ResolvedVisualMatch, ...]: ...


class VisualIntegrationBridge:
    def __init__(self, client: VisualAIClient, catalogue: CatalogueReader) -> None:
        self.client, self.catalogue = client, catalogue

    async def search(
        self, image: bytes, *, mime_type: str, top_k: int = 5
    ) -> tuple[ResolvedVisualMatch, ...]:
        ranked = await self.client.search(image, mime_type=mime_type, top_k=top_k)
        resolved = await self.catalogue.resolve(ranked)
        if len(resolved) != len(ranked.matches):
            raise BridgeError("canonical_resolution_failure")
        seen = set()
        for match, product in zip(ranked.matches, resolved, strict=True):
            if (match.rank, match.score, match.external_product_id, match.external_image_id) != (
                product.rank,
                product.score,
                product.external_product_id,
                product.external_image_id,
            ):
                raise BridgeError("ranking_violation")
            if product.product.product_id in seen:
                raise BridgeError("ambiguous_identity")
            seen.add(product.product.product_id)
        return resolved
