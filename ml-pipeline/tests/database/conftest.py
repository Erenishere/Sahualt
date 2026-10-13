from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass

import pytest

from sahulat_database.integrity_review import build_integrity_review
from sahulat_database.migrations import (
    DatabaseConfig,
    apply_migration,
    load_database_config,
    run_psql,
)
from sahulat_database.verification import build_validation_report


@dataclass(frozen=True)
class MigratedDatabase:
    config: DatabaseConfig
    initial_report: dict[str, object]
    integrity_report: dict[str, object]


@pytest.fixture(scope="session")
def migrated_database() -> MigratedDatabase:
    if os.environ.get("RUN_DATABASE_TESTS") != "1":
        pytest.skip("set RUN_DATABASE_TESTS=1 to run PostgreSQL schema tests")

    try:
        base_config = load_database_config()
    except (FileNotFoundError, ValueError) as error:
        pytest.skip(str(error))

    database_name = f"sahulat_ai_m001_test_{uuid.uuid4().hex[:12]}"
    assert re.fullmatch(r"[a-z0-9_]+", database_name)
    admin_config = base_config.for_database("postgres")
    run_psql(admin_config, sql=f'CREATE DATABASE "{database_name}";')
    test_config = base_config.for_database(database_name)
    try:
        apply_migration(test_config)
        initial_report = build_validation_report(test_config, require_empty_business_tables=True)
        integrity_report = build_integrity_review(test_config)
        yield MigratedDatabase(test_config, initial_report, integrity_report)
    finally:
        run_psql(
            admin_config,
            sql=f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE);',
            check=True,
        )
