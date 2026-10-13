from __future__ import annotations

from collections.abc import Mapping, Sequence

from sahulat_text.contracts import SourceRank, TextMatch


def reciprocal_rank_fusion(
    rankings: Mapping[str, Sequence[str]],
    *,
    k: int = 60,
    top_k: int,
) -> tuple[TextMatch, ...]:
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise ValueError("k must be a positive integer")
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
        raise ValueError("top_k must be a positive integer")
    if not rankings:
        raise ValueError("rankings must include at least one branch")
    for source, products in rankings.items():
        if not isinstance(source, str) or not source.strip():
            raise ValueError("branch source must be a non-empty string")
        seen: set[str] = set()
        for product_id in products:
            if not isinstance(product_id, str) or not product_id.strip():
                raise ValueError("product_id must be a non-empty string")
            if product_id in seen:
                raise ValueError(f"duplicate product_id in branch {source}")
            seen.add(product_id)

    scores: dict[str, float] = {}
    source_ranks: dict[str, dict[str, int]] = {source: {} for source in rankings}
    for source, products in rankings.items():
        for rank, product_id in enumerate(products, start=1):
            scores[product_id] = scores.get(product_id, 0.0) + 1.0 / (k + rank)
            source_ranks[source][product_id] = rank

    ordered = sorted(
        scores.items(),
        key=lambda item: (-item[1], item[0]),
    )[:top_k]
    matches: list[TextMatch] = []
    for product_id, score in ordered:
        ranks = tuple(
            SourceRank(source, source_ranks[source][product_id])
            for source in sorted(rankings)
            if product_id in source_ranks[source]
        )
        matches.append(TextMatch(product_id=product_id, score=score, source_ranks=ranks))
    return tuple(matches)
