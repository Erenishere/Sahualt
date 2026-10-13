from __future__ import annotations

import json
from collections.abc import Iterable
from uuid import UUID

from sahulat_database.migrations import DatabaseConfig, query_json, run_psql

from .config import DenseRetrieverConfig
from .encoder import TextEncoder
from .errors import DenseRetrieverError
from .models import DenseIndexRecord


def records_from_searchable_texts(
    encoder: TextEncoder,
    config: DenseRetrieverConfig,
    *,
    product_ids: tuple[str, ...],
    searchable_texts: tuple[str, ...],
    corpus_sha256: str,
) -> tuple[DenseIndexRecord, ...]:
    if len(product_ids) != len(searchable_texts):
        raise DenseRetrieverError("product_ids and searchable_texts length mismatch")
    if (
        encoder.encoder_id != config.encoder_id
        or encoder.encoder_revision != config.encoder_revision
    ):
        raise DenseRetrieverError("encoder identity disagrees with dense config")
    if encoder.dimension != config.vector_dimension:
        raise DenseRetrieverError("encoder dimension disagrees with dense config")
    vectors = encoder.encode(searchable_texts)
    if vectors.shape != (len(searchable_texts), config.vector_dimension):
        raise DenseRetrieverError("encoder output dimension mismatch")
    rows: list[DenseIndexRecord] = []
    for product_id, vector in zip(product_ids, vectors, strict=True):
        rows.append(
            DenseIndexRecord(
                UUID(product_id),
                tuple(float(value) for value in vector.tolist()),
                corpus_sha256.removeprefix("sha256:"),
                config.document_schema_version,
                config.encoder_id,
                config.encoder_revision,
            )
        )
    identities = [row.product_id for row in rows]
    if len(identities) != len(set(identities)):
        raise DenseRetrieverError("duplicate product_id in dense index batch")
    return tuple(sorted(rows, key=lambda row: str(row.product_id)))


def rebuild_dense_index(
    db: DatabaseConfig,
    config: DenseRetrieverConfig,
    records: Iterable[DenseIndexRecord],
) -> dict[str, object]:
    rows = tuple(records)
    if not rows:
        raise DenseRetrieverError("refusing to build an empty dense index")
    for row in rows:
        if len(row.embedding) != config.vector_dimension:
            raise DenseRetrieverError("embedding dimension mismatch")
        if (
            row.encoder_id != config.encoder_id
            or row.encoder_revision != config.encoder_revision
            or row.document_schema_version != config.document_schema_version
        ):
            raise DenseRetrieverError("dense index record metadata mismatch")
    corpus_values = {row.corpus_sha256 for row in rows}
    if len(corpus_values) != 1:
        raise DenseRetrieverError("mixed corpus_sha256 values in one rebuild")
    corpus_sha256 = next(iter(corpus_values))
    payload = [
        {
            "product_id": str(row.product_id),
            "document_schema_version": row.document_schema_version,
            "corpus_sha256": row.corpus_sha256,
            "encoder_id": row.encoder_id,
            "encoder_revision": row.encoder_revision,
            "embedding": list(row.embedding),
        }
        for row in rows
    ]
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    delimiter = "$dense_index$"
    if delimiter in encoded:
        raise DenseRetrieverError("payload delimiter collision")
    sql = f"""
DO $body$
DECLARE
    row record;
    vector_text text;
BEGIN
    TRUNCATE search.product_text_dense_v1;
    FOR row IN
        SELECT *
        FROM json_to_recordset({delimiter}{encoded}{delimiter})
            AS payload(
                product_id uuid,
                document_schema_version text,
                corpus_sha256 text,
                encoder_id text,
                encoder_revision text,
                embedding json
            )
    LOOP
        vector_text := '[' || (
            SELECT string_agg(value::text, ',')
            FROM json_array_elements_text(row.embedding) AS value
        ) || ']';
        EXECUTE format(
            'INSERT INTO search.product_text_dense_v1 (
                product_id,
                document_schema_version,
                corpus_sha256,
                encoder_id,
                encoder_revision,
                embedding
            ) VALUES ($1, $2, $3, $4, $5, $6::vector(3))'
        )
        USING
            row.product_id,
            row.document_schema_version,
            row.corpus_sha256,
            row.encoder_id,
            row.encoder_revision,
            vector_text;
    END LOOP;
END
$body$;
"""
    run_psql(db, stdin_sql=sql)
    status = query_json(
        db,
        f"""
SELECT json_build_object(
    'indexed', (SELECT count(*)::int FROM search.product_text_dense_v1),
    'corpus_sha256', '{corpus_sha256}',
    'encoder_id', '{config.encoder_id.replace("'", "''")}',
    'encoder_revision', '{config.encoder_revision.replace("'", "''")}'
);
""",
    )
    indexed = status.get("indexed")
    if not isinstance(indexed, int) or indexed != len(rows):
        raise DenseRetrieverError("indexed row count mismatch after dense rebuild")
    return status
