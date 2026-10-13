"""Apply Migration 002 (search lexical FTS prototype schema)."""

from __future__ import annotations

import argparse
from pathlib import Path

from sahulat_database.migrations import (
    SEARCH_LEXICAL_MIGRATION_ID,
    SEARCH_LEXICAL_MIGRATION_PATH,
    apply_migration,
    load_database_config,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply search lexical FTS migration (002)")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--database", help="Override DATABASE_NAME")
    args = parser.parse_args()
    config = load_database_config(args.env_file, database_override=args.database)
    result = apply_migration(
        config,
        migration_path=SEARCH_LEXICAL_MIGRATION_PATH,
        migration_id=SEARCH_LEXICAL_MIGRATION_ID,
    )
    if result.stdout.strip():
        print(result.stdout.strip())
    print(f"Migration {SEARCH_LEXICAL_MIGRATION_ID} is current on database {config.database}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
