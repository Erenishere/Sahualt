from __future__ import annotations

from pathlib import Path

from sahulat_database.migrations import DatabaseConfig, query_json

from .config import DenseRetrieverConfig
from .errors import DenseRetrieverError

FROZEN_EVAL_QUERIES = Path("artifacts/eval_text_v1/queries.jsonl")


def assert_search_dense_migration_applied(db: DatabaseConfig, config: DenseRetrieverConfig) -> None:
    migration_id = config.migration_id.replace("'", "''")
    status = query_json(
        db,
        f"""
SELECT json_build_object(
    'applied', EXISTS (
        SELECT 1 FROM integration.schema_migrations WHERE migration_id = '{migration_id}'
    ),
    'table_ready', EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'search' AND table_name = 'product_text_dense_v1'
    ),
    'vector_extension', EXISTS (
        SELECT 1 FROM pg_extension WHERE extname = 'vector'
    )
);
""",
    )
    if not status.get("vector_extension"):
        raise DenseRetrieverError("pgvector extension is not installed on this PostgreSQL host")
    if not status.get("applied") or not status.get("table_ready"):
        raise DenseRetrieverError(
            "search dense migration is not applied; run apply_search_dense_migration.py"
        )


def assert_prototype_corpus_index_allowed(*, confirm_infrastructure: bool) -> None:
    if not confirm_infrastructure:
        raise DenseRetrieverError(
            "full corpus indexing requires --confirm-infrastructure-index-only "
            "(prototype track; not official EVAL-TEXT-V1 execution)"
        )
    if FROZEN_EVAL_QUERIES.exists():
        raise DenseRetrieverError(
            "frozen EVAL-TEXT-V1 queries exist; defer full-corpus dense indexing "
            "until coordinator confirms infrastructure-only use, or use --toy"
        )


def assert_prototype_smoke_query(query: str) -> None:
    if not isinstance(query, str) or not query.strip():
        raise DenseRetrieverError("smoke query must be nonblank developer text")
    if len(query) > 512:
        raise DenseRetrieverError("smoke query exceeds length bound")
    if "txt-q-" in query.casefold():
        raise DenseRetrieverError("smoke query must not reference benchmark query identifiers")
