from __future__ import annotations

import pytest

from sahulat_text import TextRetriever
from sahulat_text.retrievers.dense import (
    PostgresDenseRetriever,
    create_prototype_encoder,
    load_prototype_config,
)
from sahulat_text.retrievers.dense.errors import DenseRetrieverError

TOY_CORPUS = "b" * 64


@pytest.mark.unit
def test_postgres_dense_retriever_is_text_retriever_protocol() -> None:
    config = load_prototype_config()
    encoder = create_prototype_encoder(config.vector_dimension)
    retriever = PostgresDenseRetriever(
        object(),  # type: ignore[arg-type]
        config,
        encoder,
        corpus_sha256=TOY_CORPUS,
    )
    assert isinstance(retriever, TextRetriever)
    assert retriever.index_version.endswith(TOY_CORPUS)


@pytest.mark.unit
def test_dense_search_rejects_empty_query_and_top_k() -> None:
    config = load_prototype_config()
    encoder = create_prototype_encoder(config.vector_dimension)
    retriever = PostgresDenseRetriever(
        object(),  # type: ignore[arg-type]
        config,
        encoder,
        corpus_sha256=TOY_CORPUS,
    )
    with pytest.raises(DenseRetrieverError):
        retriever.search("", 3)
    with pytest.raises(DenseRetrieverError):
        retriever.search("red shirt", 0)


@pytest.mark.unit
def test_dense_retriever_rejects_invalid_corpus_hash() -> None:
    config = load_prototype_config()
    encoder = create_prototype_encoder(config.vector_dimension)
    with pytest.raises(DenseRetrieverError):
        PostgresDenseRetriever(
            object(),  # type: ignore[arg-type]
            config,
            encoder,
            corpus_sha256="not-a-sha256",
        )
