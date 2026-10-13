from __future__ import annotations

import pytest

from sahulat_text.retrievers.dense.errors import DenseRetrieverError
from sahulat_text.retrievers.dense.guards import assert_prototype_smoke_query


@pytest.mark.unit
def test_dense_smoke_query_blocks_benchmark_tokens() -> None:
    with pytest.raises(DenseRetrieverError):
        assert_prototype_smoke_query("lookup TXT-Q-0040 style")


@pytest.mark.unit
def test_dense_smoke_query_allows_developer_text() -> None:
    assert_prototype_smoke_query("red shirt")
