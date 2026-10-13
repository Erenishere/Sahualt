from dataclasses import replace

import numpy as np
import pytest

from sahulat_visual.domain import ImageMatch, ImageRecord, normalize
from sahulat_visual.errors import EmptyIndexError, IndexCompatibilityError
from sahulat_visual.index import InMemoryVectorIndex
from sahulat_visual.retrieval import VisualRetrievalService, aggregate_products

pytestmark = pytest.mark.unit


def test_normalization():
    values = normalize(np.array([[3, 4], [0, 2]], dtype=np.float32))
    np.testing.assert_allclose(values, [[0.6, 0.8], [0, 1]])
    assert values.dtype == np.float32


@pytest.mark.parametrize("bad", [[0, 0], [float("nan"), 1], [float("inf"), 1]])
def test_invalid_normalization(bad):
    with pytest.raises(IndexCompatibilityError):
        normalize(np.array(bad))


def test_normalization_extreme_finite_values():
    np.testing.assert_allclose(normalize(np.array([3e30, 4e30])), [0.6, 0.8])


def test_max_aggregation_suppresses_products_and_orders():
    matches = [
        ImageMatch(ImageRecord("a1", "a", "a1.png"), 0.4),
        ImageMatch(ImageRecord("b1", "b", "b1.png"), 0.7),
        ImageMatch(ImageRecord("a2", "a", "a2.png"), 0.9),
    ]
    products = aggregate_products(matches, 2)
    assert [p.product_id for p in products] == ["a", "b"]
    assert products[0].matched_image_id == "a2"
    assert products[0].score == 0.9


def test_ties_are_deterministic():
    matches = [
        ImageMatch(ImageRecord(i, p, f"{i}.png"), 0.5)
        for i, p in [("b2", "b"), ("a2", "a"), ("a1", "a")]
    ]
    assert aggregate_products(matches, 1)[0].matched_image_id == "a1"


def test_index_ranking_and_roundtrip(encoder, tmp_path):
    records = [ImageRecord("b", "B", "b.png"), ImageRecord("a", "A", "a.png")]
    index = InMemoryVectorIndex(encoder.identity, np.array([[1, 0, 0], [1, 0, 0]]), records)
    assert [m.record.image_id for m in index.search(np.array([1, 0, 0]), 2, encoder.identity)] == [
        "a",
        "b",
    ]
    path = tmp_path / "index.npz"
    index.save(path)
    restored = InMemoryVectorIndex.load(path)
    assert restored.search(np.array([-1, 0, 0]), 1, encoder.identity)[0].score == -1
    assert restored.identity == encoder.identity


def test_dimension_validation(encoder):
    with pytest.raises(IndexCompatibilityError):
        InMemoryVectorIndex(encoder.identity, np.ones((1, 2)), [ImageRecord("a", "A", "a.png")])
    index = InMemoryVectorIndex(encoder.identity, np.ones((1, 3)), [ImageRecord("a", "A", "a.png")])
    with pytest.raises(IndexCompatibilityError):
        index.search(np.ones(2), 1, encoder.identity)


@pytest.mark.parametrize(
    "field,value",
    [
        ("model_version", "other"),
        ("preprocessing", "other"),
        ("embedding_version", "other"),
        ("weights", "other"),
    ],
)
def test_incompatible_versions_rejected(encoder, field, value):
    index = InMemoryVectorIndex(encoder.identity, np.ones((1, 3)), [ImageRecord("a", "A", "a.png")])
    with pytest.raises(IndexCompatibilityError):
        index.search(np.ones(3), 1, replace(encoder.identity, **{field: value}))


def test_empty_index(encoder):
    index = InMemoryVectorIndex(encoder.identity, np.empty((0, 3)), [])
    with pytest.raises(EmptyIndexError):
        index.search(np.ones(3), 1, encoder.identity)


@pytest.mark.parametrize("k", [0, -2, True, 2.1])
def test_service_invalid_k(encoder, k):
    index = InMemoryVectorIndex(encoder.identity, np.empty((0, 3)), [])
    with pytest.raises(ValueError):
        VisualRetrievalService(encoder, index).search(b"bad", k)


def test_service_expands_neighbors(encoder, image_file):
    path = image_file("query.png", (255, 0, 0))
    records = [ImageRecord(f"a{i}", "A", f"a{i}.png") for i in range(8)]
    records.append(ImageRecord("b", "B", "b.png"))
    vectors = np.array([[1, 0, 0]] * 8 + [[0.8, 0.2, 0]])
    index = InMemoryVectorIndex(encoder.identity, vectors, records)
    products = VisualRetrievalService(encoder, index, image_top_k=2).search(path, 2)
    assert [p.product_id for p in products] == ["A", "B"]


def test_service_expands_score_ties(encoder, image_file):
    records = [ImageRecord("a", "Z", "a.png"), ImageRecord("z", "A", "z.png")]
    index = InMemoryVectorIndex(encoder.identity, np.array([[1, 0, 0]] * 2), records)
    products = VisualRetrievalService(encoder, index, 1).search(image_file("q.png"), 1)
    assert products[0].product_id == "A"


def test_missing_product_metadata_rejected():
    with pytest.raises(ValueError):
        ImageRecord("a", "", "a.png")
