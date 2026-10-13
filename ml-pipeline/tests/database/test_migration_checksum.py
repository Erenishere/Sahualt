from __future__ import annotations

from pathlib import Path

import pytest

from sahulat_database.migrations import migration_checksum

pytestmark = pytest.mark.unit


def test_migration_checksum_is_stable_across_line_endings(tmp_path: Path) -> None:
    lf_path = tmp_path / "lf.sql"
    crlf_path = tmp_path / "crlf.sql"
    lf_path.write_bytes(b"SELECT 1;\nSELECT 2;\n")
    crlf_path.write_bytes(b"SELECT 1;\r\nSELECT 2;\r\n")

    assert migration_checksum(lf_path) == migration_checksum(crlf_path)


def test_migration_checksum_changes_with_sql_semantics(tmp_path: Path) -> None:
    first_path = tmp_path / "first.sql"
    second_path = tmp_path / "second.sql"
    first_path.write_text("SELECT 1;\n", encoding="utf-8")
    second_path.write_text("SELECT 2;\n", encoding="utf-8")

    assert migration_checksum(first_path) != migration_checksum(second_path)
