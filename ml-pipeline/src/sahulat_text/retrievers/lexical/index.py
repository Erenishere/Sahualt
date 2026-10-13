from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from sahulat_database.migrations import DatabaseConfig, query_json, run_psql
from sahulat_text.documents.builder import SCHEMA_VERSION, ProductTextDocument

from .config import LexicalRetrieverConfig
from .errors import LexicalRetrieverError

_CORPUS_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class LexicalIndexDocument:
    product_id: UUID
    searchable_text: str
    corpus_sha256: str
    document_schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.searchable_text, str) or not self.searchable_text.strip():
            raise LexicalRetrieverError("searchable_text must be nonblank")
        if not _CORPUS_SHA256.fullmatch(self.corpus_sha256):
            raise LexicalRetrieverError("corpus_sha256 must be lowercase sha256 hex")


def documents_from_product_text(
    documents: Iterable[ProductTextDocument], *, corpus_sha256: str
) -> tuple[LexicalIndexDocument, ...]:
    normalized = corpus_sha256.removeprefix("sha256:")
    rows = [
        LexicalIndexDocument(document.product_id, document.text, normalized)
        for document in documents
    ]
    identities = [row.product_id for row in rows]
    if len(identities) != len(set(identities)):
        raise LexicalRetrieverError("duplicate product_id in lexical index batch")
    return tuple(sorted(rows, key=lambda row: str(row.product_id)))


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def rebuild_lexical_index(
    config: DatabaseConfig,
    lexical_config: LexicalRetrieverConfig,
    documents: Iterable[LexicalIndexDocument],
) -> dict[str, int]:
    rows = tuple(documents)
    if not rows:
        raise LexicalRetrieverError("refusing to build an empty lexical index")
    for row in rows:
        if row.document_schema_version != lexical_config.document_schema_version:
            raise LexicalRetrieverError("document schema version mismatch")
    payload = [
        {
            "product_id": str(row.product_id),
            "document_schema_version": row.document_schema_version,
            "corpus_sha256": row.corpus_sha256,
            "searchable_text": row.searchable_text,
        }
        for row in rows
    ]
    corpus_values = {row.corpus_sha256 for row in rows}
    if len(corpus_values) != 1:
        raise LexicalRetrieverError("mixed corpus_sha256 values in one rebuild")
    corpus_sha256 = next(iter(corpus_values))
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    delimiter = "$lexical_index$"
    if delimiter in encoded:
        raise LexicalRetrieverError("payload delimiter collision")
    sql = f"""
DO $body$
DECLARE
    row record;
BEGIN
    TRUNCATE search.product_text_lexical_v1;
    FOR row IN
        SELECT *
        FROM json_to_recordset({delimiter}{encoded}{delimiter})
            AS payload(
                product_id uuid,
                document_schema_version text,
                corpus_sha256 text,
                searchable_text text
            )
    LOOP
        INSERT INTO search.product_text_lexical_v1 (
            product_id,
            document_schema_version,
            corpus_sha256,
            searchable_text
        ) VALUES (
            row.product_id,
            row.document_schema_version,
            row.corpus_sha256,
            row.searchable_text
        );
    END LOOP;
END
$body$;
"""
    run_psql(config, stdin_sql=sql)
    status = query_json(
        config,
        f"""
SELECT json_build_object(
    'indexed', (SELECT count(*)::int FROM search.product_text_lexical_v1),
    'corpus_sha256', {_sql_literal(corpus_sha256)}
);
""",
    )
    indexed = status.get("indexed")
    if not isinstance(indexed, int) or indexed != len(rows):
        raise LexicalRetrieverError("indexed row count mismatch after rebuild")
    return {"indexed": indexed, "corpus_sha256": corpus_sha256}
