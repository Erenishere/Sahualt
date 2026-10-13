from dataclasses import FrozenInstanceError

import pytest

from sahulat_text import SourceRank, TextMatch, TextRetriever


class FixtureRetriever:
    retriever_id = "fixture-v1"
    index_version = "product-text-v1:fixture"

    def search(self, query: str, top_k: int) -> list[TextMatch]:
        return [TextMatch("SKU-1", 1.0, (SourceRank("fixture", 1),))][:top_k]


@pytest.mark.unit
def test_contract_supports_structural_retriever_implementations() -> None:
    retriever = FixtureRetriever()

    assert isinstance(retriever, TextRetriever)
    assert retriever.search("red shirt", 1) == [
        TextMatch("SKU-1", 1.0, (SourceRank("fixture", 1),))
    ]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("product_id", "score"),
    [("", 1.0), ("SKU-1", float("nan")), ("SKU-1", float("inf")), ("SKU-1", True)],
)
def test_text_match_rejects_invalid_identity_or_score(product_id: str, score: float) -> None:
    with pytest.raises(ValueError):
        TextMatch(product_id, score)


@pytest.mark.unit
def test_source_ranks_are_validated_and_immutable() -> None:
    match = TextMatch("SKU-1", 0.5, (SourceRank("lexical", 1), SourceRank("dense", 2)))

    with pytest.raises(FrozenInstanceError):
        match.score = 0.8  # type: ignore[misc]
    with pytest.raises(ValueError, match="each source"):
        TextMatch("SKU-1", 0.5, (SourceRank("dense", 1), SourceRank("dense", 2)))
