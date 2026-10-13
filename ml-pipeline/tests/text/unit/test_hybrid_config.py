from __future__ import annotations

import pytest

from sahulat_text.retrievers.hybrid.config import HybridRetrieverConfig, load_prototype_config


@pytest.mark.unit
def test_load_prototype_hybrid_config() -> None:
    config = load_prototype_config()
    assert config.retriever_id == "hybrid-rrf-text-prototype-v1"
    assert config.rrf_k == 60


@pytest.mark.unit
def test_hybrid_config_rejects_invalid_rrf_k() -> None:
    with pytest.raises(ValueError, match="rrf_k"):
        HybridRetrieverConfig.from_mapping(
            {
                "version": "v",
                "retriever_id": "r",
                "rrf_k": 0,
                "lexical_branch_source": "lexical",
                "dense_branch_source": "dense",
                "branch_depth": 10,
                "document_schema_version": "product-text-v1",
            }
        )
