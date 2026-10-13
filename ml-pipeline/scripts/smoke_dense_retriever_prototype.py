"""Developer smoke search against prototype dense index (synthetic queries only)."""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from pathlib import Path

from sahulat_database.migrations import load_database_config
from sahulat_text.retrievers.dense import (
    DenseRetrieverError,
    PostgresDenseRetriever,
    create_prototype_encoder,
    load_prototype_config,
)
from sahulat_text.retrievers.dense.guards import (
    assert_prototype_smoke_query,
    assert_search_dense_migration_applied,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prototype dense smoke search")
    parser.add_argument("--query", required=True, help="Developer-only query text")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument(
        "--corpus-sha256",
        default="b" * 64,
        help="Corpus hash bound to indexed rows (toy default: 64 x b)",
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--database", help="Override DATABASE_NAME")
    args = parser.parse_args(argv)
    try:
        assert_prototype_smoke_query(args.query)
        config = load_prototype_config()
        db = load_database_config(args.env_file, database_override=args.database)
        assert_search_dense_migration_applied(db, config)
        encoder = create_prototype_encoder(config.vector_dimension)
        retriever = PostgresDenseRetriever(
            db,
            config,
            encoder,
            corpus_sha256=args.corpus_sha256,
        )
        matches = retriever.search(args.query, args.top_k)
    except DenseRetrieverError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("prototype dense smoke search")
    print(f"Query: {args.query}")
    print(f"Matches: {len(matches)}")
    for index, match in enumerate(matches, start=1):
        print(f"{index}. {match.product_id} score={match.score:.4f}")
        print(asdict(match))
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
