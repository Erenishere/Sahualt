"""Rebuild pgvector dense index for prototype Baseline B (not official EVAL-TEXT-V1)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sahulat_database.migrations import load_database_config
from sahulat_text.documents.corpus import DEFAULT_REGISTRY
from sahulat_text.retrievers.dense import (
    DenseRetrieverError,
    create_prototype_encoder,
    load_prototype_config,
    rebuild_dense_index,
    records_from_searchable_texts,
)
from sahulat_text.retrievers.dense.corpus_load import (
    load_lexical_documents_from_registry,
    toy_lexical_documents,
)
from sahulat_text.retrievers.dense.guards import (
    assert_prototype_corpus_index_allowed,
    assert_search_dense_migration_applied,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prototype dense pgvector index rebuild")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--toy", action="store_true", help="Index synthetic toy catalogue")
    source.add_argument(
        "--corpus-registry",
        type=Path,
        nargs="?",
        const=DEFAULT_REGISTRY,
        help="Index verified product-text-v1 with infrastructure confirmation",
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--database", help="Override DATABASE_NAME")
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument(
        "--confirm-infrastructure-index-only",
        action="store_true",
        help="Required with --corpus-registry",
    )
    args = parser.parse_args(argv)
    try:
        config = load_prototype_config()
        db = load_database_config(args.env_file, database_override=args.database)
        assert_search_dense_migration_applied(db, config)
        encoder = create_prototype_encoder(config.vector_dimension)
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
        corpus_sha256 = documents[0].corpus_sha256
        records = records_from_searchable_texts(
            encoder,
            config,
            product_ids=tuple(str(row.product_id) for row in documents),
            searchable_texts=tuple(row.searchable_text for row in documents),
            corpus_sha256=corpus_sha256,
        )
        summary = rebuild_dense_index(db, config, records)
    except (DenseRetrieverError, ValueError, OSError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print(
        "\n".join(
            [
                "postgresql-dense index rebuild (prototype)",
                "",
                f"Source: {source_label}",
                f"Indexed: {summary['indexed']}",
                f"Corpus SHA-256: {summary['corpus_sha256']}",
                f"Encoder: {summary['encoder_id']} @ {summary['encoder_revision']}",
                f"Migration: {config.migration_id}",
                "",
                "PASS",
            ]
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
