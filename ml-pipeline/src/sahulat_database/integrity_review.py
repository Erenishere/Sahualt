from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .migrations import MIGRATION_PATH, DatabaseConfig, migration_checksum, query_json
from .verification import build_validation_report

REQUIRED_CONSTRAINTS = {
    "ck_inventory_on_hand_non_negative",
    "ck_inventory_reserved_within_on_hand",
    "ck_listings_active_commercial_state",
    "ck_listings_price_non_negative",
    "fk_product_images_variant_product",
    "uq_product_external_refs_source_external",
}
REQUIRED_INDEXES = {"uq_product_variants_default_active"}
INTENTIONAL_PREFIX_OVERLAPS = {
    (
        "catalog",
        "product_variants",
        "product_variants_pkey",
        "uq_product_variants_id_product",
    ): "Composite uniqueness is required as the target of the same-product image foreign key.",
}


def _index_details(config: DatabaseConfig) -> list[dict[str, Any]]:
    result = query_json(
        config,
        """
        SELECT COALESCE(jsonb_agg(to_jsonb(q) ORDER BY schema_name, table_name, index_name),
                              '[]'::jsonb)
        FROM (
            SELECT
                namespace.nspname AS schema_name,
                relation.relname AS table_name,
                index_relation.relname AS index_name,
                access_method.amname AS method,
                index_row.indisunique AS is_unique,
                index_row.indisprimary AS is_primary,
                constraint_row.conname AS constraint_name,
                ARRAY(
                    SELECT pg_get_indexdef(index_row.indexrelid, position, true)
                    FROM generate_series(1, index_row.indnkeyatts) AS position
                    ORDER BY position
                ) AS key_columns,
                pg_get_expr(index_row.indpred, index_row.indrelid) AS predicate
            FROM pg_index AS index_row
            JOIN pg_class AS relation ON relation.oid = index_row.indrelid
            JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
            JOIN pg_class AS index_relation ON index_relation.oid = index_row.indexrelid
            JOIN pg_am AS access_method ON access_method.oid = index_relation.relam
            LEFT JOIN pg_constraint AS constraint_row
                ON constraint_row.conindid = index_row.indexrelid
               AND constraint_row.conrelid = index_row.indrelid
               AND constraint_row.contype IN ('p', 'u', 'x')
            WHERE namespace.nspname IN ('iam', 'catalog', 'inventory', 'integration', 'audit')
        ) AS q;
        """,
    )
    if not isinstance(result, list):
        raise TypeError("Expected index catalog query to return a JSON array")
    return result


def _index_overlap_analysis(indexes: list[dict[str, Any]]) -> dict[str, Any]:
    exact_duplicates: list[dict[str, Any]] = []
    prefix_candidates: list[dict[str, Any]] = []

    for position, left in enumerate(indexes):
        for right in indexes[position + 1 :]:
            if (
                left["schema_name"],
                left["table_name"],
                left["method"],
                left["predicate"],
            ) != (
                right["schema_name"],
                right["table_name"],
                right["method"],
                right["predicate"],
            ):
                continue

            left_keys = tuple(left["key_columns"])
            right_keys = tuple(right["key_columns"])
            names = sorted((left["index_name"], right["index_name"]))
            common = {
                "schema_name": left["schema_name"],
                "table_name": left["table_name"],
                "indexes": names,
                "predicate": left["predicate"],
            }
            if left_keys == right_keys:
                exact_duplicates.append(common)
                continue

            shorter, longer = (left_keys, right_keys)
            if len(shorter) > len(longer):
                shorter, longer = longer, shorter
            if longer[: len(shorter)] != shorter:
                continue

            lookup_key = (
                left["schema_name"],
                left["table_name"],
                names[0],
                names[1],
            )
            prefix_candidates.append(
                {
                    **common,
                    "shorter_key": list(shorter),
                    "longer_key": list(longer),
                    "classification": (
                        "INTENTIONAL"
                        if lookup_key in INTENTIONAL_PREFIX_OVERLAPS
                        else "REVIEW_REQUIRED"
                    ),
                    "reason": INTENTIONAL_PREFIX_OVERLAPS.get(lookup_key),
                }
            )

    return {
        "total": len(indexes),
        "constraint_backed": sum(index["constraint_name"] is not None for index in indexes),
        "explicit": sum(index["constraint_name"] is None for index in indexes),
        "exact_duplicates": exact_duplicates,
        "prefix_candidates": prefix_candidates,
    }


def build_integrity_review(config: DatabaseConfig) -> dict[str, Any]:
    validation = build_validation_report(config)
    indexes = _index_details(config)
    index_analysis = _index_overlap_analysis(indexes)
    constraints = {row["constraint_name"]: row for row in validation["constraints"]}
    index_names = {row["index_name"] for row in indexes}

    role_posture = query_json(
        config,
        """
        SELECT jsonb_build_object(
            'current_role', current_user,
            'current_role_superuser', (
                SELECT rolsuper FROM pg_roles WHERE rolname = current_user
            ),
            'non_system_login_roles', COALESCE((
                SELECT jsonb_agg(
                    jsonb_build_object('role', rolname, 'superuser', rolsuper)
                    ORDER BY rolname
                )
                FROM pg_roles
                WHERE rolcanlogin AND rolname !~ '^pg_'
            ), '[]'::jsonb),
            'public_table_privilege_count', (
                SELECT count(*)
                FROM information_schema.role_table_grants
                WHERE grantee = 'PUBLIC'
                  AND table_schema IN ('iam', 'catalog', 'inventory', 'integration', 'audit')
            )
        );
        """,
    )
    migration_record = next(
        row for row in validation["migrations"] if row["migration_id"] == validation["migration_id"]
    )
    audit_foreign_keys = [
        row
        for row in validation["constraints"]
        if row["schema_name"] == "audit" and row["constraint_type"] == "FOREIGN KEY"
    ]
    cascade_foreign_keys = sorted(
        row["constraint_name"]
        for row in validation["constraints"]
        if row["constraint_type"] == "FOREIGN KEY" and row["delete_action"] == "CASCADE"
    )

    checks = {
        "same_product_variant_image_fk": "fk_product_images_variant_product" in constraints,
        "single_unarchived_default_variant": ("uq_product_variants_default_active" in index_names),
        "inventory_null_and_bounds_constraints": {
            "ck_inventory_on_hand_non_negative",
            "ck_inventory_reserved_within_on_hand",
        }.issubset(constraints),
        "draft_listing_allows_null_currency": any(
            row["column_name"] == "currency"
            and row["schema_name"] == "catalog"
            and row["table_name"] == "listings"
            and row["nullable"]
            for row in validation["columns"]
        ),
        "active_listing_commercial_state_constrained": (
            "ck_listings_active_commercial_state" in constraints
        ),
        "audit_foreign_keys_preserve_history": bool(audit_foreign_keys)
        and all(row["delete_action"] == "SET NULL" for row in audit_foreign_keys),
        "only_external_lineage_refs_cascade": cascade_foreign_keys
        == ["fk_image_external_refs_image", "fk_product_external_refs_product"],
        "external_product_identity_unique": (
            "uq_product_external_refs_source_external" in constraints
        ),
        "no_exact_duplicate_indexes": not index_analysis["exact_duplicates"],
        "all_prefix_overlaps_justified": all(
            row["classification"] == "INTENTIONAL" for row in index_analysis["prefix_candidates"]
        ),
        "migration_checksum_matches_source": (
            migration_record["checksum"] == migration_checksum(MIGRATION_PATH)
        ),
        "public_has_no_table_privileges": role_posture["public_table_privilege_count"] == 0,
        "required_constraints_present": REQUIRED_CONSTRAINTS.issubset(constraints),
        "required_indexes_present": REQUIRED_INDEXES.issubset(index_names),
        "base_schema_validation_green": validation["status"] == "GREEN",
    }
    deferred = {
        "least_privilege_application_role": (
            "No application login role exists. postgres is migration/local administration only; "
            "create a non-superuser runtime role before backend or worker deployment."
        ),
        "audit_append_only_grants": (
            "PUBLIC currently has no privileges. When runtime roles are introduced, grant audit "
            "INSERT/SELECT as needed and withhold UPDATE, DELETE, and TRUNCATE."
        ),
    }
    status = "GREEN" if all(checks.values()) else "RED"
    return {
        "review_version": "db-contract-v1-integrity-review",
        "status": status,
        "database": validation["database"],
        "postgresql_version": validation["postgresql_version"],
        "generated_at": validation["generated_at"],
        "checks": checks,
        "deferred_runtime_controls": deferred,
        "role_posture": role_posture,
        "cascade_foreign_keys": cascade_foreign_keys,
        "audit_foreign_keys": audit_foreign_keys,
        "index_analysis": index_analysis,
        "indexes": indexes,
        "migration": migration_record,
    }


def render_integrity_markdown(report: dict[str, Any]) -> str:
    analysis = report["index_analysis"]
    lines = [
        "# DB-CONTRACT-V1 Integrity Review",
        "",
        f"Status: **{report['status']}**  ",
        f"Review version: `{report['review_version']}`  ",
        f"Database: `{report['database']}` on PostgreSQL `{report['postgresql_version']}`  ",
        f"Generated (UTC): `{report['generated_at']}`",
        "",
        "## Integrity checks",
        "",
    ]
    lines.extend(
        f"- {name}: {'PASS' if passed else 'FAIL'}" for name, passed in report["checks"].items()
    )
    lines.extend(
        [
            "",
            "## Index review",
            "",
            f"- Total indexes: {analysis['total']}",
            f"- Constraint-backed: {analysis['constraint_backed']}",
            f"- Explicit: {analysis['explicit']}",
            f"- Exact duplicates: {len(analysis['exact_duplicates'])}",
            f"- Prefix candidates: {len(analysis['prefix_candidates'])}",
            "",
        ]
    )
    for overlap in analysis["prefix_candidates"]:
        lines.append(
            f"- `{overlap['indexes'][0]}` / `{overlap['indexes'][1]}`: "
            f"**{overlap['classification']}** — {overlap['reason']}"
        )
    lines.extend(
        [
            "",
            "No exact duplicate index exists. The only same-predicate left-prefix overlap is",
            "retained because PostgreSQL requires the composite unique target used by the",
            "same-product ProductImage foreign key.",
            "",
            "## Security boundary",
            "",
            "The live database currently has only the `postgres` login role and PUBLIC has no",
            "table privileges on the five application schemas. `postgres` is explicitly an",
            "administration/migration identity, not the future application identity.",
            "",
            "Deferred before runtime/backend deployment:",
            "",
        ]
    )
    lines.extend(f"- {value}" for value in report["deferred_runtime_controls"].values())
    lines.extend(
        [
            "",
            "These are role-provisioning controls, not contradictions in Migration 001. The",
            "schema contract is frozen; changing schema semantics requires a new migration.",
            "",
        ]
    )
    return "\n".join(lines)


def write_integrity_review(report: dict[str, Any], *, json_path: Path, markdown_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_integrity_markdown(report), encoding="utf-8")
