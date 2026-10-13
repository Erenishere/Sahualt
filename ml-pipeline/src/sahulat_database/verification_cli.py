from __future__ import annotations

import argparse
from pathlib import Path

from .migrations import load_database_config
from .verification import build_validation_report, write_validation_reports


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify Sahulat AI Database Contract V1")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--database", help="Override DATABASE_NAME")
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path("reports/database_schema_validation_v1.json"),
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=Path("reports/database_schema_validation_v1.md"),
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    config = load_database_config(args.env_file, database_override=args.database)
    report = build_validation_report(config)
    write_validation_reports(
        report,
        json_path=args.json_output,
        markdown_path=args.markdown_output,
    )
    print(f"Database Contract V1 validation: {report['status']}")
    return 0 if report["status"] == "GREEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
