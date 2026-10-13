from __future__ import annotations

import pytest

from sahulat_text.retrievers.dense.config import load_prototype_config


@pytest.mark.unit
def test_prototype_config_loads_expected_identity() -> None:
    config = load_prototype_config()
    assert config.retriever_id == "postgresql-dense-prototype-v1"
    assert config.vector_dimension == 3
    assert config.encoder_id == "toy-text-encoder-v1"
