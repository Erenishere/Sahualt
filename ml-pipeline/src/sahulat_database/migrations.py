from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

DEFAULT_WINDOWS_PSQL = Path(r"C:\Program Files\PostgreSQL\18\bin\psql.exe")
MIGRATION_ID = "20260910_001_catalog_core_v1"
MIGRATION_PATH = Path("database/migrations/20260910_001_catalog_core_v1.sql")
SEARCH_LEXICAL_MIGRATION_ID = "20260926_002_search_lexical_v1"
SEARCH_LEXICAL_MIGRATION_PATH = Path(
    "database/migrations/20260926_002_search_lexical_v1.sql"
)
SEARCH_DENSE_MIGRATION_ID = "20260926_003_text_dense_prototype_v1"
SEARCH_DENSE_MIGRATION_PATH = Path(
    "database/migrations/20260926_003_text_dense_prototype_v1.sql"
)


@dataclass(frozen=True)
class DatabaseConfig:
    host: str
    port: int
    database: str
    user: str
    password: str = field(repr=False)
    psql: Path

    def for_database(self, database: str) -> DatabaseConfig:
        return replace(self, database=database)


def _read_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def _setting(name: str, dotenv: dict[str, str]) -> str:
    value = os.environ.get(name, dotenv.get(name, ""))
    if not value:
        raise ValueError(f"Required database setting is missing: {name}")
    return value


def _find_psql() -> Path:
    configured = os.environ.get("PSQL_PATH")
    if configured:
        path = Path(configured)
    else:
        discovered = shutil.which("psql")
        path = Path(discovered) if discovered else DEFAULT_WINDOWS_PSQL
    if not path.is_file():
        raise FileNotFoundError(
            "psql was not found. Set PSQL_PATH to the PostgreSQL client executable."
        )
    return path


def load_database_config(
    dotenv_path: Path = Path(".env"), *, database_override: str | None = None
) -> DatabaseConfig:
    dotenv = _read_dotenv(dotenv_path)
    database = database_override or _setting("DATABASE_NAME", dotenv)
    port_text = _setting("DATABASE_PORT", dotenv)
    try:
        port = int(port_text)
    except ValueError as error:
        raise ValueError("DATABASE_PORT must be an integer") from error
    if not 1 <= port <= 65535:
        raise ValueError("DATABASE_PORT must be between 1 and 65535")

    return DatabaseConfig(
        host=_setting("DATABASE_HOST", dotenv),
        port=port,
        database=database,
        user=_setting("DATABASE_USER", dotenv),
        password=_setting("DATABASE_PASSWORD", dotenv),
        psql=_find_psql(),
    )


def run_psql(
    config: DatabaseConfig,
    *,
    sql: str | None = None,
    file: Path | None = None,
    stdin_sql: str | None = None,
    variables: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    inputs_provided = sum(value is not None for value in (sql, file, stdin_sql))
    if inputs_provided != 1:
        raise ValueError("Provide exactly one of sql, file, or stdin_sql")

    command = [
        str(config.psql),
        "-X",
        "-w",
        "-v",
        "ON_ERROR_STOP=1",
        "-h",
        config.host,
        "-p",
        str(config.port),
        "-U",
        config.user,
        "-d",
        config.database,
    ]
    for key, value in sorted((variables or {}).items()):
        command.extend(["-v", f"{key}={value}"])
    if file is not None:
        command.extend(["-f", str(file.resolve())])
    elif sql is not None:
        command.extend(["-At", "-c", sql or ""])
    else:
        command.append("-At")

    process_env = os.environ.copy()
    process_env["PGPASSWORD"] = config.password
    process_env["PGCONNECT_TIMEOUT"] = "10"
    process_env["PGCLIENTENCODING"] = "UTF8"
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=process_env,
        input=stdin_sql,
    )
    if completed.returncode == 0:
        if "Migration checksum mismatch:" in completed.stdout:
            completed.returncode = 3
        elif "migration_id is required" in completed.stdout:
            completed.returncode = 2
        elif "migration_checksum is required" in completed.stdout:
            completed.returncode = 2
    if check and completed.returncode != 0:
        raise subprocess.CalledProcessError(
            completed.returncode,
            completed.args,
            output=completed.stdout,
            stderr=completed.stderr,
        )
    return completed


def migration_checksum(path: Path) -> str:
    normalized = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def apply_migration(
    config: DatabaseConfig,
    migration_path: Path = MIGRATION_PATH,
    migration_id: str = MIGRATION_ID,
) -> subprocess.CompletedProcess[str]:
    if not migration_path.is_file():
        raise FileNotFoundError(f"Migration file not found: {migration_path}")
    return run_psql(
        config,
        file=migration_path,
        variables={
            "migration_checksum": migration_checksum(migration_path),
            "migration_id": migration_id,
        },
    )


def query_json(config: DatabaseConfig, sql: str) -> Any:
    completed = run_psql(config, sql=sql)
    output = completed.stdout.strip()
    if not output:
        raise RuntimeError("PostgreSQL query returned no JSON output")
    return json.loads(output)
