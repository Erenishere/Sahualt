from __future__ import annotations

import argparse
from pathlib import Path

from .integrity_review import build_integrity_review, write_integrity_review
from .migrations import load_database_config


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review DB-CONTRACT-V1 integrity")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--database", help="Override DATABASE_NAME")
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path("reports/database_integrity_review_v1.json"),
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=Path("reports/database_integrity_review_v1.md"),
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    config = load_database_config(args.env_file, database_override=args.database)
    report = build_integrity_review(config)
    write_integrity_review(
        report,
        json_path=args.json_output,
        markdown_path=args.markdown_output,
    )
    print(f"DB-CONTRACT-V1 integrity review: {report['status']}")
    return 0 if report["status"] == "GREEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
