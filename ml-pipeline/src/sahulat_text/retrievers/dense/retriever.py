from __future__ import annotations

import re
from math import isfinite

from sahulat_database.migrations import DatabaseConfig, query_json
from sahulat_text.contracts import SourceRank, TextMatch

from .config import DenseRetrieverConfig
from .encoder import TextEncoder
from .errors import DenseRetrieverError


class PostgresDenseRetriever:
    """Prototype Baseline B using pgvector exact cosine scan."""

    def __init__(
        self,
        db: DatabaseConfig,
        config: DenseRetrieverConfig,
        encoder: TextEncoder,
        *,
        corpus_sha256: str,
    ) -> None:
        normalized = corpus_sha256.removeprefix("sha256:")
        if not re.fullmatch(r"[0-9a-f]{64}", normalized):
            raise DenseRetrieverError("corpus_sha256 must be lowercase sha256 hex")
        if (
            encoder.encoder_id != config.encoder_id
            or encoder.encoder_revision != config.encoder_revision
            or encoder.dimension != config.vector_dimension
        ):
            raise DenseRetrieverError("encoder identity/dimension disagrees with config")
        self._db = db
        self._config = config
        self._encoder = encoder
        self._corpus_sha256 = normalized
        self._index_version = (
            f"{config.document_schema_version}:{config.migration_id}:"
            f"{config.encoder_id}:{config.encoder_revision}:{normalized}"
        )

    @property
    def retriever_id(self) -> str:
        return self._config.retriever_id

    @property
    def index_version(self) -> str:
        return self._index_version

    def search(self, query: str, top_k: int) -> tuple[TextMatch, ...]:
        if not isinstance(query, str) or not query.strip():
            raise DenseRetrieverError("query must be nonblank")
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
            raise DenseRetrieverError("top_k must be a positive integer")
        if len(query) > 512:
            raise DenseRetrieverError("query exceeds prototype length bound")

        vector = self._encoder.encode([query])[0]
        if vector.shape[0] != self._config.vector_dimension:
            raise DenseRetrieverError("query embedding dimension mismatch")
        literal = "[" + ",".join(f"{float(value):.8f}" for value in vector.tolist()) + "]"
        encoder_id = self._config.encoder_id.replace("'", "''")
        encoder_revision = self._config.encoder_revision.replace("'", "''")
        sql = f"""
WITH q AS (
    SELECT '{literal}'::vector(3) AS query_vec
),
ranked AS (
    SELECT
        lower(d.product_id::text) AS product_id,
        (1 - (d.embedding <=> q.query_vec))::float8 AS score,
        row_number() OVER (
            ORDER BY d.embedding <=> q.query_vec ASC, lower(d.product_id::text) ASC
        ) AS rank
    FROM search.product_text_dense_v1 d
    CROSS JOIN q
    WHERE d.corpus_sha256 = '{self._corpus_sha256}'
      AND d.encoder_id = '{encoder_id}'
      AND d.encoder_revision = '{encoder_revision}'
    ORDER BY d.embedding <=> q.query_vec ASC, lower(d.product_id::text) ASC
    LIMIT {top_k}
)
SELECT COALESCE(
    json_agg(
        json_build_object('product_id', product_id, 'score', score, 'rank', rank)
        ORDER BY rank ASC
    ),
    '[]'::json
)
FROM ranked;
"""
        rows = query_json(self._db, sql)
        if not isinstance(rows, list):
            raise DenseRetrieverError("unexpected dense search payload")
        matches: list[TextMatch] = []
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                raise DenseRetrieverError("invalid dense search row")
            product_id = row.get("product_id")
            score = row.get("score")
            rank = row.get("rank")
            if not isinstance(product_id, str) or not product_id.strip() or product_id in seen:
                raise DenseRetrieverError("duplicate or invalid product_id in dense results")
            if (
                isinstance(score, bool)
                or not isinstance(score, (int, float))
                or not isfinite(score)
            ):
                raise DenseRetrieverError("invalid dense score")
            if isinstance(rank, bool) or not isinstance(rank, int) or rank < 1:
                raise DenseRetrieverError("invalid dense rank")
            seen.add(product_id)
            matches.append(
                TextMatch(
                    product_id=product_id,
                    score=float(score),
                    source_ranks=(SourceRank("dense", rank),),
                )
            )
        return tuple(matches)
