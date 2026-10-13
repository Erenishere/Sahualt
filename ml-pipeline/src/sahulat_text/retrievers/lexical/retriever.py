from __future__ import annotations

import re
from math import isfinite

from sahulat_database.migrations import DatabaseConfig, query_json
from sahulat_text.contracts import SourceRank, TextMatch

from .config import LexicalRetrieverConfig
from .errors import LexicalRetrieverError


class PostgresLexicalRetriever:
    """Prototype Baseline A: PostgreSQL FTS only; not official EVAL-TEXT-V1 execution."""

    def __init__(
        self,
        db: DatabaseConfig,
        config: LexicalRetrieverConfig,
        *,
        corpus_sha256: str,
    ) -> None:
        normalized = corpus_sha256.removeprefix("sha256:")
        if not re.fullmatch(r"[0-9a-f]{64}", normalized):
            raise LexicalRetrieverError("corpus_sha256 must be lowercase sha256 hex")
        self._db = db
        self._config = config
        self._corpus_sha256 = normalized
        self._index_version = f"{config.document_schema_version}:{config.migration_id}:{normalized}"

    @property
    def retriever_id(self) -> str:
        return self._config.retriever_id

    @property
    def index_version(self) -> str:
        return self._index_version

    def search(self, query: str, top_k: int) -> tuple[TextMatch, ...]:
        if not isinstance(query, str) or not query.strip():
            raise LexicalRetrieverError("query must be nonblank")
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
            raise LexicalRetrieverError("top_k must be a positive integer")
        if len(query) > 512:
            raise LexicalRetrieverError("query exceeds prototype length bound")

        literal = "'" + query.replace("'", "''") + "'"
        config = self._config.text_search_config
        rank = self._config.rank_function
        sql = f"""
WITH parsed AS (
    SELECT websearch_to_tsquery('{config}', {literal}) AS query
),
ranked AS (
    SELECT
        lower(d.product_id::text) AS product_id,
        {rank}(d.document_tsvector, p.query)::float8 AS score,
        row_number() OVER (
            ORDER BY {rank}(d.document_tsvector, p.query) DESC,
                     lower(d.product_id::text) ASC
        ) AS rank
    FROM search.product_text_lexical_v1 d
    CROSS JOIN parsed p
    WHERE d.corpus_sha256 = '{self._corpus_sha256}'
      AND d.document_tsvector @@ p.query
    ORDER BY score DESC, product_id ASC
    LIMIT {top_k}
)
SELECT COALESCE(
    json_agg(
        json_build_object('product_id', product_id, 'score', score, 'rank', rank)
        ORDER BY score DESC, product_id ASC
    ),
    '[]'::json
)
FROM ranked;
"""
        rows = query_json(self._db, sql)
        if not isinstance(rows, list):
            raise LexicalRetrieverError("unexpected lexical search payload")
        matches: list[TextMatch] = []
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                raise LexicalRetrieverError("invalid lexical search row")
            product_id = row.get("product_id")
            score = row.get("score")
            rank = row.get("rank")
            if not isinstance(product_id, str) or not product_id.strip() or product_id in seen:
                raise LexicalRetrieverError("duplicate or invalid product_id in results")
            if (
                isinstance(score, bool)
                or not isinstance(score, (int, float))
                or not isfinite(score)
            ):
                raise LexicalRetrieverError("invalid lexical score")
            if isinstance(rank, bool) or not isinstance(rank, int) or rank < 1:
                raise LexicalRetrieverError("invalid lexical rank")
            seen.add(product_id)
            matches.append(
                TextMatch(
                    product_id=product_id,
                    score=float(score),
                    source_ranks=(SourceRank("lexical", rank),),
                )
            )
        return tuple(matches)
