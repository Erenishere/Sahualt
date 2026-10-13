from __future__ import annotations

from uuid import UUID

import pytest

from sahulat_text.retrievers.dense import (
    create_prototype_encoder,
    load_prototype_config,
    records_from_searchable_texts,
)
from sahulat_text.retrievers.dense.errors import DenseRetrieverError
from sahulat_text.retrievers.dense.models import DenseIndexRecord

TOY_CORPUS = "b" * 64


@pytest.mark.unit
def test_records_from_searchable_texts_builds_unique_rows() -> None:
    config = load_prototype_config()
    encoder = create_prototype_encoder(config.vector_dimension)
    records = records_from_searchable_texts(
        encoder,
        config,
        product_ids=(
            "00000000-0000-7000-8000-000000000101",
            "00000000-0000-7000-8000-000000000102",
        ),
        searchable_texts=("red cotton shirt", "blue running shoes"),
        corpus_sha256=TOY_CORPUS,
    )
    assert len(records) == 2
    assert len({record.product_id for record in records}) == 2


@pytest.mark.unit
def test_records_reject_duplicate_product_id() -> None:
    config = load_prototype_config()
    encoder = create_prototype_encoder(config.vector_dimension)
    with pytest.raises(DenseRetrieverError, match="duplicate"):
        records_from_searchable_texts(
            encoder,
            config,
            product_ids=(
                "00000000-0000-7000-8000-000000000101",
                "00000000-0000-7000-8000-000000000101",
            ),
            searchable_texts=("red cotton shirt", "red shirt"),
            corpus_sha256=TOY_CORPUS,
        )


@pytest.mark.unit
def test_dense_index_record_validates_corpus_hash() -> None:
    with pytest.raises(DenseRetrieverError):
        DenseIndexRecord(
            UUID(int=1),
            (1.0, 0.0, 0.0),
            "not-valid",
            "product-text-v1",
            "toy-text-encoder-v1",
            "deterministic-keyword-v1",
        )
