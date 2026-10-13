from __future__ import annotations

import pytest

from sahulat_database.migrations import (
    SEARCH_DENSE_MIGRATION_ID,
    SEARCH_DENSE_MIGRATION_PATH,
    apply_migration,
)
from sahulat_text import TextRetriever
from sahulat_text.retrievers.dense import (
    PostgresDenseRetriever,
    create_prototype_encoder,
    load_prototype_config,
    rebuild_dense_index,
    records_from_searchable_texts,
)
from sahulat_text.retrievers.dense.corpus_load import toy_lexical_documents

pytestmark = pytest.mark.database

TOY_CORPUS_SHA256 = "b" * 64


@pytest.fixture(scope="session")
def dense_database(migrated_database):
    config = migrated_database.config
    try:
        apply_migration(
            config,
            migration_path=SEARCH_DENSE_MIGRATION_PATH,
            migration_id=SEARCH_DENSE_MIGRATION_ID,
        )
    except Exception as error:  # noqa: BLE001 - surface pgvector install hint
        pytest.skip(f"dense migration unavailable: {error}")
    return config


@pytest.mark.database
def test_synthetic_toy_dense_cosine_ranking(dense_database) -> None:
    db = dense_database
    dense_config = load_prototype_config()
    encoder = create_prototype_encoder(dense_config.vector_dimension)
    documents = toy_lexical_documents(corpus_sha256=TOY_CORPUS_SHA256)
    records = records_from_searchable_texts(
        encoder,
        dense_config,
        product_ids=tuple(str(row.product_id) for row in documents),
        searchable_texts=tuple(row.searchable_text for row in documents),
        corpus_sha256=TOY_CORPUS_SHA256,
    )
    summary = rebuild_dense_index(db, dense_config, records)
    assert summary["indexed"] == 3

    retriever = PostgresDenseRetriever(
        db,
        dense_config,
        encoder,
        corpus_sha256=TOY_CORPUS_SHA256,
    )
    assert isinstance(retriever, TextRetriever)

    matches = retriever.search("red shirt", top_k=3)
    assert matches
    assert matches[0].product_id == "00000000-0000-7000-8000-000000000101"
    assert matches[0].score >= matches[1].score
    assert matches[0].source_ranks[0].source == "dense"
