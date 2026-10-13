from __future__ import annotations

import pytest

from sahulat_text.retrievers.lexical.errors import LexicalRetrieverError
from sahulat_text.retrievers.lexical.guards import assert_prototype_smoke_query


@pytest.mark.unit
def test_smoke_query_rejects_benchmark_id_tokens() -> None:
    with pytest.raises(LexicalRetrieverError):
        assert_prototype_smoke_query("find TXT-Q-0001 products")


@pytest.mark.unit
def test_smoke_query_accepts_developer_text() -> None:
    assert_prototype_smoke_query("red cotton shirt")
