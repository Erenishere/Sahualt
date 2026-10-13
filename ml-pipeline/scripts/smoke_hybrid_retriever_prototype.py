"""Developer smoke search: lexical + dense RRF (synthetic queries only)."""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from pathlib import Path

from sahulat_database.migrations import load_database_config
from sahulat_text.retrievers.dense import (
    PostgresDenseRetriever,
    create_prototype_encoder,
)
from sahulat_text.retrievers.dense import (
    load_prototype_config as load_dense_config,
)
from sahulat_text.retrievers.dense.errors import DenseRetrieverError
from sahulat_text.retrievers.dense.guards import assert_search_dense_migration_applied
from sahulat_text.retrievers.hybrid import HybridRRFRetriever, load_prototype_config
from sahulat_text.retrievers.hybrid.errors import HybridRetrieverError
from sahulat_text.retrievers.lexical import PostgresLexicalRetriever
from sahulat_text.retrievers.lexical import load_prototype_config as load_lexical_config
from sahulat_text.retrievers.lexical.errors import LexicalRetrieverError
from sahulat_text.retrievers.lexical.guards import (
    assert_prototype_smoke_query,
    assert_search_lexical_migration_applied,
)

TOY_CORPUS_DEFAULT = "b" * 64


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prototype hybrid RRF smoke search")
    parser.add_argument("--query", required=True, help="Developer-only query text")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--corpus-sha256",
        default=TOY_CORPUS_DEFAULT,
        help="Corpus hash bound to indexed rows (toy default: bbbb...)",
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--database", help="Override DATABASE_NAME")
    args = parser.parse_args(argv)
    try:
        assert_prototype_smoke_query(args.query)
        hybrid_config = load_prototype_config()
        lexical_config = load_lexical_config()
        dense_config = load_dense_config()
        db = load_database_config(args.env_file, database_override=args.database)
        assert_search_lexical_migration_applied(db, lexical_config)
        assert_search_dense_migration_applied(db, dense_config)
        encoder = create_prototype_encoder(dense_config.vector_dimension)
        lexical = PostgresLexicalRetriever(db, lexical_config, corpus_sha256=args.corpus_sha256)
        dense = PostgresDenseRetriever(
            db,
            dense_config,
            encoder,
            corpus_sha256=args.corpus_sha256,
        )
        retriever = HybridRRFRetriever(lexical, dense, hybrid_config)
        matches = retriever.search(args.query, args.top_k)
    except (LexicalRetrieverError, DenseRetrieverError, HybridRetrieverError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("prototype hybrid RRF smoke search")
    print(f"Query: {args.query}")
    print(f"Matches: {len(matches)}")
    for match in matches:
        print(asdict(match))
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
