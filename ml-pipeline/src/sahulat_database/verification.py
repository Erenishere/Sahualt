from __future__ import annotations

from pathlib import Path
from typing import Any

from .migrations import MIGRATION_ID, DatabaseConfig, query_json

CORE_SCHEMAS = ("audit", "catalog", "iam", "integration", "inventory")
CORE_TABLES = (
    "audit.audit_log",
    "catalog.categories",
    "catalog.image_external_refs",
    "catalog.listings",
    "catalog.product_external_refs",
    "catalog.product_images",
    "catalog.product_variants",
    "catalog.products",
    "catalog.vendors",
    "iam.users",
    "iam.vendor_memberships",
    "integration.outbox_events",
    "integration.schema_migrations",
    "inventory.inventory_balances",
)
BUSINESS_TABLES = tuple(table for table in CORE_TABLES if table != "integration.schema_migrations")
FORBIDDEN_SCHEMAS = ("analytics", "commerce", "search")
FORBIDDEN_TABLE_NAMES = (
    "offers",
    "orders",
    "order_items",
    "product_text_documents",
    "product_text_embeddings",
    "product_image_embeddings",
    "search_queries",
    "search_results",
)


def _sql_array(values: tuple[str, ...]) -> str:
    return ", ".join("'" + value.replace("'", "''") + "'" for value in values)


def _catalog_query(config: DatabaseConfig, inner_sql: str, order_by: str) -> list[dict[str, Any]]:
    sql = f"""
    SELECT COALESCE(jsonb_agg(to_jsonb(q) ORDER BY {order_by}), '[]'::jsonb)
    FROM ({inner_sql}) AS q;
    """
    result = query_json(config, sql)
    if not isinstance(result, list):
        raise TypeError("Expected PostgreSQL catalog query to return a JSON array")
    return result


def build_validation_report(
    config: DatabaseConfig, *, require_empty_business_tables: bool = False
) -> dict[str, Any]:
    metadata = query_json(
        config,
        """
        SELECT jsonb_build_object(
            'database', current_database(),
            'postgresql_version', current_setting('server_version'),
            'generated_at', to_char(
                statement_timestamp() AT TIME ZONE 'UTC',
                'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'
            ),
            'uuidv7_available', to_regprocedure('uuidv7()') IS NOT NULL
        );
        """,
    )
    schemas = _catalog_query(
        config,
        f"""
        SELECT schema_name
        FROM information_schema.schemata
        WHERE schema_name IN ({_sql_array(CORE_SCHEMAS)})
        """,
        "schema_name",
    )
    tables = _catalog_query(
        config,
        f"""
        SELECT table_schema AS schema_name, table_name
        FROM information_schema.tables
        WHERE table_type = 'BASE TABLE'
          AND table_schema IN ({_sql_array(CORE_SCHEMAS)})
        """,
        "schema_name, table_name",
    )
    columns = _catalog_query(
        config,
        f"""
        SELECT
            table_schema AS schema_name,
            table_name,
            ordinal_position,
            column_name,
            data_type,
            udt_name,
            is_nullable = 'YES' AS nullable,
            column_default
        FROM information_schema.columns
        WHERE table_schema IN ({_sql_array(CORE_SCHEMAS)})
        """,
        "schema_name, table_name, ordinal_position",
    )
    constraints = _catalog_query(
        config,
        f"""
        SELECT
            namespace.nspname AS schema_name,
            relation.relname AS table_name,
            constraint_row.conname AS constraint_name,
            CASE constraint_row.contype
                WHEN 'p' THEN 'PRIMARY KEY'
                WHEN 'f' THEN 'FOREIGN KEY'
                WHEN 'u' THEN 'UNIQUE'
                WHEN 'c' THEN 'CHECK'
                ELSE constraint_row.contype::text
            END AS constraint_type,
            pg_get_constraintdef(constraint_row.oid, true) AS definition,
            CASE constraint_row.confdeltype
                WHEN 'a' THEN 'NO ACTION'
                WHEN 'r' THEN 'RESTRICT'
                WHEN 'c' THEN 'CASCADE'
                WHEN 'n' THEN 'SET NULL'
                WHEN 'd' THEN 'SET DEFAULT'
                ELSE NULL
            END AS delete_action
        FROM pg_constraint AS constraint_row
        JOIN pg_class AS relation ON relation.oid = constraint_row.conrelid
        JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname IN ({_sql_array(CORE_SCHEMAS)})
          AND constraint_row.contype IN ('p', 'f', 'u', 'c')
        """,
        "schema_name, table_name, constraint_type, constraint_name",
    )
    indexes = _catalog_query(
        config,
        f"""
        SELECT schemaname AS schema_name, tablename AS table_name, indexname, indexdef
        FROM pg_indexes
        WHERE schemaname IN ({_sql_array(CORE_SCHEMAS)})
        """,
        "schema_name, table_name, indexname",
    )
    migrations = _catalog_query(
        config,
        """
        SELECT migration_id, checksum, postgres_version,
               to_char(applied_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')
                   AS applied_at
        FROM integration.schema_migrations
        """,
        "migration_id",
    )

    row_counts: dict[str, int] = {}
    for qualified_table in BUSINESS_TABLES:
        schema_name, table_name = qualified_table.split(".", 1)
        count = query_json(
            config,
            f'SELECT to_jsonb(count(*)) FROM "{schema_name}"."{table_name}";',
        )
        row_counts[qualified_table] = int(count)

    forbidden = query_json(
        config,
        f"""
        SELECT jsonb_build_object(
            'schemas', COALESCE((
                SELECT jsonb_agg(schema_name ORDER BY schema_name)
                FROM information_schema.schemata
                WHERE schema_name IN ({_sql_array(FORBIDDEN_SCHEMAS)})
            ), '[]'::jsonb),
            'tables', COALESCE((
                SELECT jsonb_agg(
                    table_schema || '.' || table_name
                    ORDER BY table_schema, table_name
                )
                FROM information_schema.tables
                WHERE table_name IN ({_sql_array(FORBIDDEN_TABLE_NAMES)})
            ), '[]'::jsonb),
            'tsvector_columns', COALESCE((
                SELECT jsonb_agg(
                    table_schema || '.' || table_name || '.' || column_name
                    ORDER BY table_schema, table_name, column_name
                )
                FROM information_schema.columns
                WHERE udt_name = 'tsvector'
                  AND table_schema NOT IN ('pg_catalog', 'information_schema')
            ), '[]'::jsonb),
            'vector_extension', EXISTS (
                SELECT 1 FROM pg_extension WHERE extname = 'vector'
            )
        );
        """,
    )

    actual_schemas = [row["schema_name"] for row in schemas]
    actual_tables = [f"{row['schema_name']}.{row['table_name']}" for row in tables]
    constraint_counts = {
        constraint_type: sum(row["constraint_type"] == constraint_type for row in constraints)
        for constraint_type in ("PRIMARY KEY", "FOREIGN KEY", "UNIQUE", "CHECK")
    }
    business_tables_empty = all(count == 0 for count in row_counts.values())
    checks = {
        "expected_schemas_only": actual_schemas == list(CORE_SCHEMAS),
        "expected_tables_only": actual_tables == list(CORE_TABLES),
        "migration_recorded_once": sum(row["migration_id"] == MIGRATION_ID for row in migrations)
        == 1,
        "uuidv7_available": bool(metadata["uuidv7_available"]),
        "forbidden_schemas_absent": forbidden["schemas"] == [],
        "forbidden_tables_absent": forbidden["tables"] == [],
        "tsvector_absent": forbidden["tsvector_columns"] == [],
        "pgvector_absent": forbidden["vector_extension"] is False,
    }
    if require_empty_business_tables:
        checks["business_tables_empty"] = business_tables_empty

    return {
        "validation_version": "db-contract-v1",
        **metadata,
        "migration_id": MIGRATION_ID,
        "status": "GREEN" if all(checks.values()) else "RED",
        "checks": checks,
        "schemas": schemas,
        "tables": tables,
        "columns": columns,
        "constraints": constraints,
        "constraint_counts": constraint_counts,
        "indexes": indexes,
        "business_table_row_counts": row_counts,
        "business_tables_empty": business_tables_empty,
        "forbidden_infrastructure": forbidden,
        "migrations": migrations,
    }


def render_markdown(report: dict[str, Any]) -> str:
    counts = report["constraint_counts"]
    lines = [
        "# Database Schema Validation V1",
        "",
        f"- Status: **{report['status']}**",
        f"- Database: `{report['database']}`",
        f"- PostgreSQL: `{report['postgresql_version']}`",
        f"- Migration: `{report['migration_id']}`",
        f"- Generated (UTC): `{report['generated_at']}`",
        "",
        "## Catalog checks",
        "",
    ]
    lines.extend(
        f"- {name}: {'PASS' if passed else 'FAIL'}" for name, passed in report["checks"].items()
    )
    lines.extend(
        [
            "",
            "## Counts",
            "",
            f"- Schemas: {len(report['schemas'])}",
            f"- Tables: {len(report['tables'])}",
            f"- Primary keys: {counts['PRIMARY KEY']}",
            f"- Foreign keys: {counts['FOREIGN KEY']}",
            f"- Unique constraints: {counts['UNIQUE']}",
            f"- Check constraints: {counts['CHECK']}",
            f"- Indexes (including constraint indexes): {len(report['indexes'])}",
            "",
            "## Tables",
            "",
        ]
    )
    lines.extend(f"- `{row['schema_name']}.{row['table_name']}`" for row in report["tables"])
    lines.extend(["", "## Indexes", ""])
    lines.extend(
        f"- `{row['schema_name']}.{row['indexname']}` on `{row['table_name']}`"
        for row in report["indexes"]
    )
    lines.extend(
        [
            "",
            "The JSON companion contains every column, data type, nullability rule, default,",
            "constraint definition, foreign-key delete action, index definition, migration",
            "checksum, row count, and forbidden-infrastructure check used by this report.",
            "",
        ]
    )
    return "\n".join(lines)


def write_validation_reports(
    report: dict[str, Any],
    *,
    json_path: Path,
    markdown_path: Path,
) -> None:
    import json

    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
