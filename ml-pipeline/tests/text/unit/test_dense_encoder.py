from __future__ import annotations

import numpy as np
import pytest

from sahulat_text.retrievers.dense.encoder import ToyTextEncoder, create_prototype_encoder
from sahulat_text.retrievers.dense.errors import DenseRetrieverError


@pytest.mark.unit
def test_toy_encoder_is_deterministic_and_unit_norm() -> None:
    encoder = ToyTextEncoder()
    first = encoder.encode(["Red cotton shirt", "red cotton shirt"])
    second = encoder.encode(["Red cotton shirt", "red cotton shirt"])
    assert np.allclose(first, second)
    norms = np.linalg.norm(first, axis=1)
    assert np.allclose(norms, 1.0)


@pytest.mark.unit
def test_toy_encoder_keyword_axes() -> None:
    encoder = ToyTextEncoder()
    vectors = encoder.encode(
        [
            "Product Name: Red cotton shirt",
            "blue running shoes",
            "black leather bag",
        ]
    )
    assert vectors.shape == (3, 3)
    assert vectors[0][0] > vectors[0][1]
    assert vectors[1][1] > vectors[1][0]
    assert vectors[2][2] > vectors[2][0]


@pytest.mark.unit
def test_toy_encoder_rejects_missing_keyword_signal() -> None:
    encoder = ToyTextEncoder()
    with pytest.raises(DenseRetrieverError):
        encoder.encode(["unrelated product description only"])


@pytest.mark.unit
def test_create_prototype_encoder_dimension_gate() -> None:
    with pytest.raises(DenseRetrieverError):
        create_prototype_encoder(384)
