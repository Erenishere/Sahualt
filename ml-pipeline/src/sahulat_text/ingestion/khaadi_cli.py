from __future__ import annotations

import argparse
from pathlib import Path

from sahulat_database.migrations import load_database_config

from .khaadi.importer import execute_khaadi_ingestion, write_import_evidence


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import the frozen Khaadi v1 evaluation fixture")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--database", help="Override DATABASE_NAME")
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path("artifacts/fixture_ingestion_v1/fixture_ingestion_v1.json"),
    )
    parser.add_argument(
        "--report-output",
        type=Path,
        default=Path("reports/fixture_ingestion_v1.md"),
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    config = load_database_config(args.env_file, database_override=args.database)
    manifest = execute_khaadi_ingestion(config, repository_root=args.repository_root)
    created = write_import_evidence(
        manifest,
        json_path=args.json_output,
        markdown_path=args.report_output,
    )
    action = "created" if created else "verified"
    print(f"Fixture Ingestion V1: {manifest['status']} (evidence {action})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
