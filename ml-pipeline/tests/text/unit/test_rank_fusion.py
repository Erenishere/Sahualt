from __future__ import annotations

import pytest

from sahulat_text.retrievers.hybrid import reciprocal_rank_fusion


@pytest.mark.unit
def test_rrf_combines_two_branches_with_stable_ties() -> None:
    fused = reciprocal_rank_fusion(
        {
            "lexical": ("p2", "p1", "p3"),
            "dense": ("p1", "p3", "p2"),
        },
        k=60,
        top_k=3,
    )
    assert [match.product_id for match in fused] == ["p1", "p2", "p3"]
    assert fused[0].source_ranks[0].source == "dense"
    assert fused[0].score > fused[1].score


@pytest.mark.unit
def test_rrf_rejects_duplicate_product_in_one_branch() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        reciprocal_rank_fusion({"lexical": ("p1", "p1")}, k=60, top_k=1)
