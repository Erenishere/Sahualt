import math

import pytest

from sahulat_visual.evaluation.metrics import (
    average_precision_at_k,
    ndcg_at_k,
    precision_at_k,
    query_metrics,
    recall_at_k,
    reciprocal_rank,
    relevance,
)

pytestmark = pytest.mark.unit


def test_known_partial_ranking():
    hits = [False, True, False, True, False, True]
    assert precision_at_k(hits, 1) == 0
    assert precision_at_k(hits, 5) == 2 / 5
    assert recall_at_k(hits, 3, 5) == 2 / 3
    assert reciprocal_rank(hits) == 1 / 2
    assert average_precision_at_k(hits, 3, 5) == pytest.approx((1 / 2 + 2 / 4) / 3)
    expected = (1 / math.log2(3) + 1 / math.log2(5)) / (1 + 1 / math.log2(3) + 1 / math.log2(4))
    assert ndcg_at_k(hits, 3, 5) == pytest.approx(expected)


def test_perfect_ranking():
    assert query_metrics([True] * 5, 5) == dict.fromkeys(
        ["precision_at_1", "precision_at_5", "recall_at_5", "mrr", "map_at_5", "ndcg_at_5"], 1.0
    )


def test_no_relevant_results():
    assert all(value == 0 for value in query_metrics([False] * 6, 0).values())


def test_short_gallery_precision_uses_k():
    assert precision_at_k([True], 5) == 0.2
    assert average_precision_at_k([True], 1, 5) == 1


def test_ap_uses_min_k_total_relevant():
    assert average_precision_at_k([True] * 5, 12, 5) == 1
    assert recall_at_k([True] * 5, 12, 5) == 5 / 12


def test_mrr_is_not_truncated_at_five():
    assert reciprocal_rank([False] * 6 + [True]) == 1 / 7


def test_relevance_is_exact_product_id():
    assert relevance("AB1", ["AB1", "AB10", "ab1", "red-shirt"]) == [True, False, False, False]


@pytest.mark.parametrize("k", [0, -1, 1.5, True])
def test_invalid_k(k):
    with pytest.raises(ValueError):
        precision_at_k([True], k)
