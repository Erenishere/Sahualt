from __future__ import annotations

from pathlib import Path

from sahulat_database.migrations import DatabaseConfig, query_json

from .config import LexicalRetrieverConfig
from .errors import LexicalRetrieverError

FROZEN_EVAL_QUERIES = Path("artifacts/eval_text_v1/queries.jsonl")


def assert_search_lexical_migration_applied(
    db: DatabaseConfig, lexical_config: LexicalRetrieverConfig
) -> None:
    migration_id = lexical_config.migration_id.replace("'", "''")
    status = query_json(
        db,
        f"""
SELECT json_build_object(
    'applied', EXISTS (
        SELECT 1
        FROM integration.schema_migrations
        WHERE migration_id = '{migration_id}'
    ),
    'table_ready', EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'search'
          AND table_name = 'product_text_lexical_v1'
    )
);
""",
    )
    if not status.get("applied") or not status.get("table_ready"):
        raise LexicalRetrieverError(
            "search lexical migration is not applied; run apply_search_lexical_migration.py"
        )


def assert_prototype_corpus_index_allowed(*, confirm_infrastructure: bool) -> None:
    if not confirm_infrastructure:
        raise LexicalRetrieverError(
            "full corpus indexing requires --confirm-infrastructure-index-only "
            "(prototype track; not official EVAL-TEXT-V1 execution)"
        )
    if FROZEN_EVAL_QUERIES.exists():
        raise LexicalRetrieverError(
            "frozen EVAL-TEXT-V1 queries exist; defer full-corpus prototype indexing "
            "until coordinator confirms infrastructure-only use, or use --toy"
        )


def assert_prototype_smoke_query(query: str) -> None:
    if not isinstance(query, str) or not query.strip():
        raise LexicalRetrieverError("smoke query must be nonblank developer text")
    if len(query) > 512:
        raise LexicalRetrieverError("smoke query exceeds length bound")
    lowered = query.casefold()
    if "txt-q-" in lowered:
        raise LexicalRetrieverError("smoke query must not reference benchmark query identifiers")
