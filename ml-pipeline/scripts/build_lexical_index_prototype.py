"""Rebuild PostgreSQL FTS index for prototype Baseline A (not official EVAL-TEXT-V1)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sahulat_database.migrations import load_database_config
from sahulat_text.documents.corpus import DEFAULT_REGISTRY
from sahulat_text.retrievers.lexical import (
    LexicalRetrieverError,
    load_prototype_config,
    rebuild_lexical_index,
)
from sahulat_text.retrievers.lexical.corpus_load import (
    load_lexical_documents_from_registry,
    toy_lexical_documents,
)
from sahulat_text.retrievers.lexical.guards import (
    assert_prototype_corpus_index_allowed,
    assert_search_lexical_migration_applied,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prototype lexical FTS index rebuild")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--toy",
        action="store_true",
        help="Index the three-product synthetic developer catalogue",
    )
    source.add_argument(
        "--corpus-registry",
        type=Path,
        nargs="?",
        const=DEFAULT_REGISTRY,
        help="Index verified frozen product-text-v1 (requires infrastructure confirmation)",
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--database", help="Override DATABASE_NAME")
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path("."),
        help="Repository root for corpus registry paths",
    )
    parser.add_argument(
        "--confirm-infrastructure-index-only",
        action="store_true",
        help="Required with --corpus-registry; not an EVAL-TEXT-V1 benchmark run",
    )
    args = parser.parse_args(argv)
    try:
        lexical_config = load_prototype_config()
        db = load_database_config(args.env_file, database_override=args.database)
        assert_search_lexical_migration_applied(db, lexical_config)
        if args.toy:
            documents = toy_lexical_documents()
            source_label = "toy-catalogue-v1"
        else:
            assert_prototype_corpus_index_allowed(
                confirm_infrastructure=args.confirm_infrastructure_index_only
            )
            registry_path = args.corpus_registry or DEFAULT_REGISTRY
            documents = load_lexical_documents_from_registry(
                registry_path,
                repository_root=args.repository_root,
            )
            source_label = f"corpus:{registry_path.as_posix()}"
        summary = rebuild_lexical_index(db, lexical_config, documents)
    except (LexicalRetrieverError, ValueError, OSError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print(
        "\n".join(
            [
                "postgresql-fts lexical index rebuild (prototype)",
                "",
                f"Source: {source_label}",
                f"Indexed: {summary['indexed']}",
                f"Corpus SHA-256: {summary['corpus_sha256']}",
                f"Migration: {lexical_config.migration_id}",
                "",
                "PASS",
            ]
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
