from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from sahulat_database.migrations import DatabaseConfig, load_database_config

from .artifacts import build_database_artifacts


def _verified_fixture_lineage(config: DatabaseConfig, root: Path) -> dict[str, Any]:
    # Optional bootstrap provenance verification, outside the canonical loader and builder.
    from sahulat_text.ingestion.khaadi.mapper import map_khaadi_fixture
    from sahulat_text.ingestion.khaadi.reader import load_khaadi_authority
    from sahulat_text.ingestion.postgres import verify_batch_parity

    authority = load_khaadi_authority(root)
    mapping = map_khaadi_fixture(authority)
    parity = verify_batch_parity(config, mapping.batch)
    if parity["status"] != "GREEN":
        raise ValueError("fixture provenance parity failed; canonical source may have changed")
    return {
        "source_system": mapping.batch.external_source,
        "source_sha256": authority.source_sha256,
        "gate_1_version": authority.audit["audit_version"],
        "fixture_semantic_checksum": parity["semantic_checksum"],
        "fixture_products": len(mapping.batch.products),
        "verified_before_build": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build canonical product-text-v1 (no retrieval)")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--database", help="Override DATABASE_NAME")
    parser.add_argument(
        "--output-directory", type=Path, default=Path("artifacts/product_documents")
    )
    parser.add_argument(
        "--report-output", type=Path, default=Path("reports/product_text_v1_build.md")
    )
    parser.add_argument("--verify-khaadi-lineage", action="store_true")
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    args = parser.parse_args()
    config = load_database_config(args.env_file, database_override=args.database)
    lineage = (
        _verified_fixture_lineage(config, args.repository_root)
        if args.verify_khaadi_lineage
        else None
    )
    evidence = build_database_artifacts(
        config,
        output_directory=args.output_directory,
        report_path=args.report_output,
        fixture_lineage=lineage,
    )
    print(
        f"product-text-v1: {evidence['status']}; "
        f"documents={evidence['manifest']['counts']['documents_generated']}; "
        f"checksum={evidence['manifest']['artifact_checksum']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
