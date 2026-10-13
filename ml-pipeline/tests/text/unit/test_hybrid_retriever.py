from __future__ import annotations

from dataclasses import dataclass

import pytest

from sahulat_text import TextMatch, TextRetriever
from sahulat_text.retrievers.hybrid import HybridRRFRetriever, load_prototype_config
from sahulat_text.retrievers.hybrid.errors import HybridRetrieverError

TOY_CORPUS = "b" * 64
LEXICAL_INDEX = f"product-text-v1:20260926_002_search_lexical_v1:{TOY_CORPUS}"
DENSE_INDEX = (
    f"product-text-v1:20260926_003_text_dense_prototype_v1:"
    f"toy-text-encoder-v1:deterministic-keyword-v1:{TOY_CORPUS}"
)


@dataclass(frozen=True, slots=True)
class _StubBranch:
    retriever_id: str
    index_version: str
    ranking: tuple[str, ...]

    def search(self, query: str, top_k: int) -> tuple[TextMatch, ...]:
        depth = min(top_k, len(self.ranking))
        return tuple(
            TextMatch(product_id=product_id, score=float(depth - rank))
            for rank, product_id in enumerate(self.ranking[:depth], start=1)
        )


@pytest.mark.unit
def test_hybrid_retriever_is_text_retriever_protocol() -> None:
    config = load_prototype_config()
    hybrid = HybridRRFRetriever(
        _StubBranch("lex", LEXICAL_INDEX, ("p1", "p2")),
        _StubBranch("dense", DENSE_INDEX, ("p2", "p1")),
        config,
    )
    assert isinstance(hybrid, TextRetriever)
    assert hybrid.retriever_id == config.retriever_id


@pytest.mark.unit
def test_hybrid_fuses_branch_orderings() -> None:
    config = load_prototype_config()
    hybrid = HybridRRFRetriever(
        _StubBranch("lex", LEXICAL_INDEX, ("p2", "p1", "p3")),
        _StubBranch("dense", DENSE_INDEX, ("p1", "p3", "p2")),
        config,
    )
    fused = hybrid.search("red shirt", top_k=3)
    assert [m.product_id for m in fused] == ["p1", "p2", "p3"]
    assert fused[0].source_ranks


@pytest.mark.unit
def test_hybrid_rejects_corpus_mismatch() -> None:
    config = load_prototype_config()
    other_corpus = "c" * 64
    with pytest.raises(HybridRetrieverError, match="corpus_sha256"):
        HybridRRFRetriever(
            _StubBranch("lex", LEXICAL_INDEX, ("p1",)),
            _StubBranch(
                "dense",
                DENSE_INDEX.replace(TOY_CORPUS, other_corpus),
                ("p1",),
            ),
            config,
        )


@pytest.mark.unit
def test_hybrid_search_validation() -> None:
    config = load_prototype_config()
    hybrid = HybridRRFRetriever(
        _StubBranch("lex", LEXICAL_INDEX, ("p1",)),
        _StubBranch("dense", DENSE_INDEX, ("p1",)),
        config,
    )
    with pytest.raises(HybridRetrieverError):
        hybrid.search("", 1)
    with pytest.raises(HybridRetrieverError):
        hybrid.search("q", 0)


@pytest.mark.unit
def test_hybrid_output_products_unique() -> None:
    config = load_prototype_config()
    hybrid = HybridRRFRetriever(
        _StubBranch("lex", LEXICAL_INDEX, ("p1", "p2")),
        _StubBranch("dense", DENSE_INDEX, ("p2", "p3")),
        config,
    )
    fused = hybrid.search("shirt", top_k=3)
    ids = [m.product_id for m in fused]
    assert len(ids) == len(set(ids))
