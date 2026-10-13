"""Developer smoke search against prototype lexical index (synthetic queries only)."""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from pathlib import Path

from sahulat_database.migrations import load_database_config
from sahulat_text.retrievers.lexical import (
    LexicalRetrieverError,
    PostgresLexicalRetriever,
    load_prototype_config,
)
from sahulat_text.retrievers.lexical.guards import (
    assert_prototype_smoke_query,
    assert_search_lexical_migration_applied,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prototype lexical smoke search")
    parser.add_argument("--query", required=True, help="Developer-only query text")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--corpus-sha256",
        required=True,
        help="Corpus hash bound to the indexed rows (toy default: bbbb...)",
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--database", help="Override DATABASE_NAME")
    args = parser.parse_args(argv)
    try:
        assert_prototype_smoke_query(args.query)
        lexical_config = load_prototype_config()
        db = load_database_config(args.env_file, database_override=args.database)
        assert_search_lexical_migration_applied(db, lexical_config)
        retriever = PostgresLexicalRetriever(
            db,
            lexical_config,
            corpus_sha256=args.corpus_sha256,
        )
        matches = retriever.search(args.query, args.top_k)
    except LexicalRetrieverError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("prototype lexical smoke search")
    print(f"Query: {args.query}")
    print(f"Matches: {len(matches)}")
    for match in matches:
        print(asdict(match))
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
