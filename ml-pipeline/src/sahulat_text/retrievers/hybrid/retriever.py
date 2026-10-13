from __future__ import annotations

from collections.abc import Sequence

from sahulat_text.contracts import TextMatch, TextRetriever

from .config import HybridRetrieverConfig
from .errors import HybridRetrieverError
from .rank_fusion import reciprocal_rank_fusion


def _corpus_sha256_from_index_version(index_version: str) -> str:
    segment = index_version.rsplit(":", maxsplit=1)[-1]
    if len(segment) != 64 or not all(ch in "0123456789abcdef" for ch in segment):
        raise HybridRetrieverError(f"index_version lacks corpus sha256 suffix: {index_version}")
    return segment


class HybridRRFRetriever:
    """Baseline D prototype: fuse lexical and dense ranked lists via RRF only."""

    def __init__(
        self,
        lexical: TextRetriever,
        dense: TextRetriever,
        config: HybridRetrieverConfig,
    ) -> None:
        lexical_corpus = _corpus_sha256_from_index_version(lexical.index_version)
        dense_corpus = _corpus_sha256_from_index_version(dense.index_version)
        if lexical_corpus != dense_corpus:
            raise HybridRetrieverError("lexical and dense index_version corpus_sha256 mismatch")
        self._lexical = lexical
        self._dense = dense
        self._config = config
        self._corpus_sha256 = lexical_corpus
        self._index_version = (
            f"{config.document_schema_version}:hybrid-rrf:"
            f"{config.rrf_k}:{lexical.index_version}+{dense.index_version}"
        )

    @property
    def retriever_id(self) -> str:
        return self._config.retriever_id

    @property
    def index_version(self) -> str:
        return self._index_version

    def search(self, query: str, top_k: int) -> tuple[TextMatch, ...]:
        if not isinstance(query, str) or not query.strip():
            raise HybridRetrieverError("query must be nonblank")
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
            raise HybridRetrieverError("top_k must be a positive integer")
        if len(query) > 512:
            raise HybridRetrieverError("query exceeds prototype length bound")

        branch_depth = max(top_k, self._config.branch_depth)
        lexical_matches: Sequence[TextMatch] = self._lexical.search(query, branch_depth)
        dense_matches: Sequence[TextMatch] = self._dense.search(query, branch_depth)
        rankings = {
            self._config.lexical_branch_source: tuple(m.product_id for m in lexical_matches),
            self._config.dense_branch_source: tuple(m.product_id for m in dense_matches),
        }
        return reciprocal_rank_fusion(
            rankings,
            k=self._config.rrf_k,
            top_k=top_k,
        )
