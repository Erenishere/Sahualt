import math
from collections.abc import Sequence

from ..domain import positive_k


def relevance(query_product_id: str, gallery_product_ids: Sequence[str]) -> list[bool]:
    """The only ground truth rule for EVAL-VISUAL-V1."""
    return [product_id == query_product_id for product_id in gallery_product_ids]


def precision_at_k(relevant: Sequence[bool], k: int) -> float:
    return sum(relevant[: positive_k(k)]) / k


def recall_at_k(relevant: Sequence[bool], total_relevant: int, k: int) -> float:
    positive_k(k)
    if total_relevant < 0:
        raise ValueError("total_relevant must be non-negative")
    return sum(relevant[:k]) / total_relevant if total_relevant else 0.0


def reciprocal_rank(relevant: Sequence[bool]) -> float:
    return next((1 / rank for rank, hit in enumerate(relevant, 1) if hit), 0.0)


def average_precision_at_k(relevant: Sequence[bool], total_relevant: int, k: int) -> float:
    positive_k(k)
    if total_relevant < 0:
        raise ValueError("total_relevant must be non-negative")
    if not total_relevant:
        return 0.0
    hits = 0
    score = 0.0
    for rank, hit in enumerate(relevant[:k], 1):
        if hit:
            hits += 1
            score += hits / rank
    return score / min(k, total_relevant)


def ndcg_at_k(relevant: Sequence[bool], total_relevant: int, k: int) -> float:
    positive_k(k)
    if total_relevant < 0:
        raise ValueError("total_relevant must be non-negative")
    dcg = sum(1 / math.log2(rank + 1) for rank, hit in enumerate(relevant[:k], 1) if hit)
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(k, total_relevant) + 1))
    return dcg / ideal if ideal else 0.0


def query_metrics(relevant: Sequence[bool], total_relevant: int) -> dict[str, float]:
    return {
        "precision_at_1": precision_at_k(relevant, 1),
        "precision_at_5": precision_at_k(relevant, 5),
        "recall_at_5": recall_at_k(relevant, total_relevant, 5),
        "mrr": reciprocal_rank(relevant),
        "map_at_5": average_precision_at_k(relevant, total_relevant, 5),
        "ndcg_at_5": ndcg_at_k(relevant, total_relevant, 5),
    }
