from __future__ import annotations

from uuid import UUID

import pytest

from sahulat_text import TextRetriever
from sahulat_text.documents.builder import build_product_document
from sahulat_text.documents.projection import CanonicalProductProjection
from sahulat_text.retrievers.lexical import (
    LexicalIndexDocument,
    LexicalRetrieverError,
    PostgresLexicalRetriever,
    documents_from_product_text,
    load_prototype_config,
)

TOY_CORPUS_SHA256 = "b" * 64


def _toy_documents() -> tuple:
    projections = (
        CanonicalProductProjection(
            UUID("00000000-0000-7000-8000-000000000101"),
            "Red cotton shirt",
            "Lightweight red cotton shirt for casual wear.",
            ("Red",),
        ),
        CanonicalProductProjection(
            UUID("00000000-0000-7000-8000-000000000102"),
            "Blue running shoes",
            "Comfortable blue shoes for daily running.",
            ("Blue",),
        ),
        CanonicalProductProjection(
            UUID("00000000-0000-7000-8000-000000000103"),
            "Black leather bag",
            "Compact black leather bag.",
            tuple(),
        ),
    )
    return tuple(build_product_document(projection) for projection in projections)


@pytest.mark.unit
def test_prototype_config_loads() -> None:
    config = load_prototype_config()
    assert config.retriever_id == "postgresql-fts-lexical-prototype-v1"
    assert config.text_search_config == "english"


@pytest.mark.unit
def test_documents_from_product_text_preserves_text_and_order() -> None:
    docs = _toy_documents()
    rows = documents_from_product_text(docs, corpus_sha256=TOY_CORPUS_SHA256)
    assert len(rows) == 3
    assert rows[0].product_id < rows[1].product_id
    assert "Red cotton shirt" in rows[0].searchable_text


@pytest.mark.unit
def test_postgres_lexical_retriever_is_text_retriever_protocol() -> None:
    class DummyDb:
        pass

    retriever = PostgresLexicalRetriever(
        DummyDb(),  # type: ignore[arg-type]
        load_prototype_config(),
        corpus_sha256=TOY_CORPUS_SHA256,
    )
    assert isinstance(retriever, TextRetriever)
    assert retriever.index_version.endswith(TOY_CORPUS_SHA256)


@pytest.mark.unit
def test_search_rejects_invalid_inputs() -> None:
    retriever = PostgresLexicalRetriever(
        object(),  # type: ignore[arg-type]
        load_prototype_config(),
        corpus_sha256=TOY_CORPUS_SHA256,
    )
    with pytest.raises(LexicalRetrieverError):
        retriever.search("", 5)
    with pytest.raises(LexicalRetrieverError):
        retriever.search("red shirt", 0)


@pytest.mark.unit
def test_lexical_index_document_validates_corpus_hash() -> None:
    with pytest.raises(LexicalRetrieverError):
        LexicalIndexDocument(
            UUID(int=1),
            "Product Name: Test\nDescription: Test",
            "not-a-sha256",
        )
