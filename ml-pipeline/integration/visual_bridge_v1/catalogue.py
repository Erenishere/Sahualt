"""Bridge-specific read-only PostgreSQL snapshot; not a general catalog repository."""

import asyncio
import json
import math
import os
from typing import Any
from uuid import UUID

from sahulat_api.identity import ExternalImageReference, resolve_canonical_matches
from sahulat_database.migrations import DatabaseConfig
from sahulat_visual.domain import ProductMatch

from .errors import BridgeError
from .models import ResolvedVisualMatch, VerifiedProduct, VisualSearch, strict_json

# Metadata only, before any business read. Column grants and inherited privileges count too.
PERMISSIONS_SQL = """
SELECT (
    current_user = {user}
    AND NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = current_user
        AND (rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls))
    AND NOT has_database_privilege(current_user, current_database(), 'CREATE,TEMPORARY')
    AND NOT EXISTS (SELECT 1 FROM pg_auth_members
        WHERE member = (SELECT oid FROM pg_roles WHERE rolname = current_user))
    AND has_schema_privilege(current_user, 'catalog', 'USAGE')
    AND COALESCE(has_table_privilege(current_user,
        to_regclass('catalog.visual_product_resolution_v1'), 'SELECT'), false)
    AND NOT COALESCE(has_table_privilege(current_user,
        to_regclass('catalog.visual_product_resolution_v1'), 'SELECT WITH GRANT OPTION'), false)
    AND NOT EXISTS (
        SELECT 1 FROM pg_namespace WHERE nspname IN
            ('iam','catalog','inventory','integration','audit','public')
            AND has_schema_privilege(current_user, oid, 'CREATE'))
    AND NOT EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname IN ('iam','catalog','inventory','integration','audit')
          AND c.relkind IN ('r','p','v','m','f') AND (
            has_table_privilege(current_user, c.oid,
                'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
            OR has_any_column_privilege(current_user, c.oid, 'INSERT,UPDATE,REFERENCES')
            OR ((n.nspname <> 'catalog' OR c.relname <> 'visual_product_resolution_v1')
                AND has_any_column_privilege(current_user, c.oid, 'SELECT'))))
) AS bridge_permissions_allowed
\\gset
"""


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def snapshot_sql(config: DatabaseConfig, search: VisualSearch) -> str:
    requested = json.dumps(
        [
            {"external_product_id": m.external_product_id, "external_image_id": m.external_image_id}
            for m in search.matches
        ],
        ensure_ascii=False,
        allow_nan=False,
    )
    return (
        "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\n"
        + PERMISSIONS_SQL.format(user=sql_literal(config.user))
        + "\\if :bridge_permissions_allowed\n"
        + f"""
        SELECT jsonb_build_object('permission_ok', true, 'rows', COALESCE((
            SELECT jsonb_agg(to_jsonb(row)) FROM (
                SELECT resolution.source_system, wanted.external_product_id,
                    wanted.external_image_id, resolution.product_id, resolution.image_id,
                    resolution.name, resolution.description, resolution.blocked
                FROM jsonb_to_recordset({sql_literal(requested)}::jsonb) AS wanted(
                    external_product_id text, external_image_id text)
                JOIN catalog.visual_product_resolution_v1 resolution
                  ON resolution.source_system = {sql_literal(search.source_system)}
                 AND resolution.external_product_id = wanted.external_product_id
                 AND resolution.external_image_id = wanted.external_image_id
            ) AS row
        ), '[]'::jsonb));
        """
        + "\n\\else\nSELECT jsonb_build_object('permission_ok', false, 'rows', '[]'::jsonb);\n"
        + "\\endif\nCOMMIT;\n"
    )


def resolve_snapshot(
    search: VisualSearch, snapshot: dict[str, Any]
) -> tuple[ResolvedVisualMatch, ...]:
    if snapshot.get("permission_ok") is not True:
        raise BridgeError("database_permission_rejected")
    rows = snapshot.get("rows")
    if not isinstance(rows, list):
        raise BridgeError("catalog_state_invalid")
    if len(rows) > len(search.matches):
        raise BridgeError("ambiguous_identity")
    references = []
    products: dict[UUID, VerifiedProduct] = {}
    try:
        for row in rows:
            if (
                set(row)
                != {
                    "source_system",
                    "external_product_id",
                    "external_image_id",
                    "product_id",
                    "image_id",
                    "name",
                    "description",
                    "blocked",
                }
                or row["blocked"] is not False
            ):
                raise BridgeError("catalog_state_invalid")
            name, description = row["name"], row["description"]
            if (
                not isinstance(name, str)
                or not name.strip()
                or not isinstance(description, str)
                or not description.strip()
            ):
                raise BridgeError("catalog_state_invalid")
            product = VerifiedProduct(UUID(row["product_id"]), name, description)
            if product.product_id in products and products[product.product_id] != product:
                raise BridgeError("catalog_state_invalid")
            products[product.product_id] = product
            references.append(
                ExternalImageReference(
                    row["source_system"],
                    row["external_product_id"],
                    row["external_image_id"],
                    product.product_id,
                    UUID(row["image_id"]),
                )
            )
        # Empty path is an unused adapter field, never reconstructed from image identity.
        matches = [
            ProductMatch(m.external_product_id, m.score, m.external_image_id, "")
            for m in search.matches
        ]
        canonical = resolve_canonical_matches(search.source_system, matches, references)
        return tuple(
            ResolvedVisualMatch(
                m.rank,
                m.score,
                m.external_product_id,
                m.external_image_id,
                resolved.matched_image_id,
                products[resolved.product_id],
            )
            for m, resolved in zip(search.matches, canonical, strict=True)
        )
    except (KeyError, ValueError, TypeError, AttributeError):
        raise BridgeError("canonical_resolution_failure") from None


class ReadOnlyCatalogue:
    def __init__(self, config: DatabaseConfig, *, timeout_seconds: float = 15.0) -> None:
        if config.user.casefold() == "postgres":
            raise BridgeError("database_permission_rejected")
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise BridgeError("invalid_configuration")
        self.config, self.timeout_seconds = config, timeout_seconds

    async def resolve(self, search: VisualSearch) -> tuple[ResolvedVisualMatch, ...]:
        command = [
            str(self.config.psql),
            "-X",
            "-qAt",
            "-w",
            "-v",
            "ON_ERROR_STOP=1",
            "-h",
            self.config.host,
            "-p",
            str(self.config.port),
            "-U",
            self.config.user,
            "-d",
            self.config.database,
        ]
        env = os.environ.copy()
        env.update(
            {
                "PGPASSWORD": self.config.password,
                "PGCLIENTENCODING": "UTF8",
                "PGCONNECT_TIMEOUT": "5",
                "PGOPTIONS": "-c default_transaction_read_only=on -c statement_timeout=10000 "
                "-c lock_timeout=3000 -c standard_conforming_strings=on -c search_path=pg_catalog",
            }
        )
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        except OSError:
            raise BridgeError("database_unavailable") from None
        try:
            async with asyncio.timeout(self.timeout_seconds):
                output, _ = await process.communicate(
                    snapshot_sql(self.config, search).encode("utf-8")
                )
            if process.returncode != 0:
                raise BridgeError("database_unavailable")
            if len(output) > 2 * 1024 * 1024:
                raise BridgeError("catalog_state_invalid")
            return resolve_snapshot(search, strict_json(output.strip()))
        except TimeoutError:
            raise BridgeError("database_timeout") from None
        finally:
            if process.returncode is None:
                process.kill()
                await asyncio.shield(process.communicate())
