from __future__ import annotations

import pytest

from sahulat_database.migrations import (
    SEARCH_LEXICAL_MIGRATION_ID,
    SEARCH_LEXICAL_MIGRATION_PATH,
    apply_migration,
)
from sahulat_text import TextRetriever
from sahulat_text.retrievers.lexical import (
    PostgresLexicalRetriever,
    load_prototype_config,
    rebuild_lexical_index,
    toy_lexical_documents,
)

TOY_CORPUS_SHA256 = "b" * 64

pytestmark = pytest.mark.database


@pytest.fixture(scope="session")
def lexical_database(migrated_database):
    config = migrated_database.config
    apply_migration(
        config,
        migration_path=SEARCH_LEXICAL_MIGRATION_PATH,
        migration_id=SEARCH_LEXICAL_MIGRATION_ID,
    )
    return config


@pytest.mark.database
def test_synthetic_toy_catalog_lexical_search(lexical_database) -> None:
    config = lexical_database
    lexical_config = load_prototype_config()
    docs = toy_lexical_documents(corpus_sha256=TOY_CORPUS_SHA256)
    summary = rebuild_lexical_index(config, lexical_config, docs)
    assert summary["indexed"] == 3

    retriever = PostgresLexicalRetriever(config, lexical_config, corpus_sha256=TOY_CORPUS_SHA256)
    assert isinstance(retriever, TextRetriever)

    red_matches = retriever.search("red shirt", top_k=3)
    assert red_matches
    assert red_matches[0].product_id == "00000000-0000-7000-8000-000000000101"
    assert red_matches[0].source_ranks[0].source == "lexical"

    shoe_matches = retriever.search("blue running shoes", top_k=1)
    assert shoe_matches[0].product_id == "00000000-0000-7000-8000-000000000102"
