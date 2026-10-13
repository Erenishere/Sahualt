import logging
from collections.abc import Sequence
from pathlib import Path
from time import perf_counter

from .domain import ImageMatch, ProductMatch, positive_k
from .encoders.base import VisualEncoder
from .errors import EmptyIndexError, IndexCompatibilityError
from .images import DEFAULT_POLICY, ImagePolicy, load_image
from .index import VectorIndex


def aggregate_products(matches: Sequence[ImageMatch], top_k: int) -> list[ProductMatch]:
    """MAX similarity; deterministic ties use product ID then matched image ID."""
    positive_k(top_k)
    best: dict[str, ImageMatch] = {}
    for match in matches:
        previous = best.get(match.record.product_id)
        if previous is None or (-match.score, match.record.image_id) < (
            -previous.score,
            previous.record.image_id,
        ):
            best[match.record.product_id] = match
    ordered = sorted(
        best.values(), key=lambda m: (-m.score, m.record.product_id, m.record.image_id)
    )
    return [
        ProductMatch(m.record.product_id, m.score, m.record.image_id, m.record.image_path)
        for m in ordered[:top_k]
    ]


class VisualRetrievalService:
    def __init__(
        self,
        encoder: VisualEncoder,
        index: VectorIndex,
        image_top_k: int = 25,
        policy: ImagePolicy = DEFAULT_POLICY,
    ) -> None:
        if encoder.identity != index.identity:
            raise IndexCompatibilityError("Service encoder does not match index")
        self.encoder = encoder
        self.index = index
        self.image_top_k = positive_k(image_top_k)
        self.policy = policy

    def search(self, image: Path | bytes, top_k: int = 5) -> list[ProductMatch]:
        positive_k(top_k)
        if not self.index.count:
            raise EmptyIndexError("No catalogue vectors are indexed")
        start = perf_counter()
        with load_image(image, self.policy) as decoded:
            vector = self.encoder.encode_image(decoded)
        count = min(self.index.count, max(top_k, self.image_top_k))
        while True:
            neighbors = self.index.search(vector, count, self.encoder.identity)
            products = aggregate_products(neighbors, top_k)
            # Expand ties too, otherwise product-ID tie ordering depends on image_top_k.
            complete = len(products) >= top_k and neighbors[-1].score < products[-1].score
            if complete or count == self.index.count:
                break
            count = min(self.index.count, count * 2)
        logging.getLogger(__name__).info(
            "retrieval_completed",
            extra={
                "embedding_version": self.encoder.identity.embedding_version,
                "indexed_vectors": self.index.count,
                "image_top_k": count,
                "products_returned": len(products),
                "latency_ms": (perf_counter() - start) * 1000,
            },
        )
        return products
