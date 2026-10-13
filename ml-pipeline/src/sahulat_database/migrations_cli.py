from __future__ import annotations

import argparse
from pathlib import Path

from .migrations import MIGRATION_ID, apply_migration, load_database_config


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply Sahulat AI PostgreSQL migrations")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--database", help="Override DATABASE_NAME")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    config = load_database_config(args.env_file, database_override=args.database)
    result = apply_migration(config)
    if result.stdout.strip():
        print(result.stdout.strip())
    print(f"Migration {MIGRATION_ID} is current on database {config.database}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
