from __future__ import annotations

import os
import re
import uuid
import pytest

from sahulat_database.migrations import (
    MIGRATION_ID,
    MIGRATION_PATH,
    DatabaseConfig,
    run_psql,
)
from sahulat_database.verification import CORE_SCHEMAS, CORE_TABLES, build_validation_report

from .conftest import MigratedDatabase

pytestmark = pytest.mark.database


@pytest.fixture(scope="session")
def seeded_database(migrated_database: MigratedDatabase) -> DatabaseConfig:
    config = migrated_database.config
    run_psql(
        config,
        sql="""
        INSERT INTO iam.users (
            id, email, email_normalized, password_hash, display_name, status
        ) VALUES (
            '00000000-0000-7000-8000-000000000001',
            'schema-tests@example.invalid',
            'schema-tests@example.invalid',
            '$argon2id$v=19$m=65536,t=3,p=4$testsalt$testhash',
            'Schema Tests',
            'active'
        );

        INSERT INTO catalog.vendors (
            id, display_name, slug, status, created_by_user_id
        ) VALUES (
            '00000000-0000-7000-8000-000000000002',
            'Test Vendor',
            'test-vendor',
            'active',
            '00000000-0000-7000-8000-000000000001'
        );

        INSERT INTO catalog.products (id, vendor_id, name, description, status)
        VALUES
            (
                '00000000-0000-7000-8000-000000000003',
                '00000000-0000-7000-8000-000000000002',
                'Product One',
                'Schema test product one',
                'draft'
            ),
            (
                '00000000-0000-7000-8000-000000000004',
                '00000000-0000-7000-8000-000000000002',
                'Product Two',
                'Schema test product two',
                'draft'
            );

        INSERT INTO catalog.product_variants (
            id, product_id, variant_code, status, is_default
        ) VALUES
            (
                '00000000-0000-7000-8000-000000000011',
                '00000000-0000-7000-8000-000000000003',
                'default',
                'active',
                true
            ),
            (
                '00000000-0000-7000-8000-000000000012',
                '00000000-0000-7000-8000-000000000004',
                'default',
                'active',
                true
            ),
            (
                '00000000-0000-7000-8000-000000000013',
                '00000000-0000-7000-8000-000000000003',
                'inventory-negative',
                'active',
                false
            ),
            (
                '00000000-0000-7000-8000-000000000014',
                '00000000-0000-7000-8000-000000000003',
                'inventory-reserved',
                'active',
                false
            ),
            (
                '00000000-0000-7000-8000-000000000015',
                '00000000-0000-7000-8000-000000000003',
                'inventory-unknown',
                'active',
                false
            );

        INSERT INTO catalog.listings (id, variant_id, status)
        VALUES
            (
                '00000000-0000-7000-8000-000000000021',
                '00000000-0000-7000-8000-000000000011',
                'draft'
            ),
            (
                '00000000-0000-7000-8000-000000000022',
                '00000000-0000-7000-8000-000000000013',
                'draft'
            ),
            (
                '00000000-0000-7000-8000-000000000023',
                '00000000-0000-7000-8000-000000000014',
                'draft'
            ),
            (
                '00000000-0000-7000-8000-000000000024',
                '00000000-0000-7000-8000-000000000015',
                'draft'
            );
        """,
    )
    return config


def assert_rejected(config: DatabaseConfig, sql: str, constraint_name: str) -> None:
    result = run_psql(config, sql=sql, check=False)
    assert result.returncode != 0
    assert constraint_name in result.stderr


def test_migration_applies_cleanly_to_empty_database(
    migrated_database: MigratedDatabase,
) -> None:
    report = migrated_database.initial_report
    assert report["status"] == "GREEN"
    assert [row["schema_name"] for row in report["schemas"]] == list(CORE_SCHEMAS)  # type: ignore[index]
    assert [
        f"{row['schema_name']}.{row['table_name']}"
        for row in report["tables"]  # type: ignore[index]
    ] == list(CORE_TABLES)


def test_db_contract_integrity_review_is_green(migrated_database: MigratedDatabase) -> None:
    review = migrated_database.integrity_report
    assert review["status"] == "GREEN"
    index_analysis = review["index_analysis"]
    assert index_analysis["total"] == 45  # type: ignore[index]
    assert index_analysis["constraint_backed"] == 22  # type: ignore[index]
    assert index_analysis["explicit"] == 23  # type: ignore[index]
    assert index_analysis["exact_duplicates"] == []  # type: ignore[index]


def test_migration_repeat_is_a_checksum_verified_no_op(
    migrated_database: MigratedDatabase,
) -> None:
    result = apply_migration(migrated_database.config)
    assert "already applied with matching checksum" in result.stdout
    count = run_psql(
        migrated_database.config,
        sql="SELECT count(*) FROM integration.schema_migrations;",
    )
    assert count.stdout.strip() == "1"


def test_migration_checksum_drift_is_rejected(migrated_database: MigratedDatabase) -> None:
    result = run_psql(
        migrated_database.config,
        file=MIGRATION_PATH,
        variables={"migration_checksum": "0" * 64, "migration_id": MIGRATION_ID},
        check=False,
    )
    assert result.returncode == 3
    assert "Migration checksum mismatch" in result.stdout


@pytest.mark.parametrize(
    ("sql", "constraint_name"),
    [
        (
            """
            INSERT INTO catalog.products (vendor_id, name, description)
            VALUES ('ffffffff-ffff-7fff-8fff-ffffffffffff', 'Invalid', 'Invalid');
            """,
            "fk_products_vendor",
        ),
        (
            """
            INSERT INTO catalog.product_variants (product_id, variant_code, is_default)
            VALUES ('ffffffff-ffff-7fff-8fff-ffffffffffff', 'invalid', false);
            """,
            "fk_product_variants_product",
        ),
        (
            """
            INSERT INTO catalog.listings (variant_id)
            VALUES ('ffffffff-ffff-7fff-8fff-ffffffffffff');
            """,
            "fk_listings_variant",
        ),
        (
            """
            INSERT INTO inventory.inventory_balances (listing_id)
            VALUES ('ffffffff-ffff-7fff-8fff-ffffffffffff');
            """,
            "fk_inventory_balances_listing",
        ),
        (
            """
            INSERT INTO catalog.product_images (product_id, storage_key, mime_type)
            VALUES (
                'ffffffff-ffff-7fff-8fff-ffffffffffff',
                'tests/missing-product.jpg',
                'image/jpeg'
            );
            """,
            "fk_product_images_product",
        ),
    ],
    ids=[
        "product-vendor",
        "variant-product",
        "listing-variant",
        "inventory-listing",
        "image-product",
    ],
)
def test_required_ownership_foreign_keys(
    migrated_database: MigratedDatabase,
    sql: str,
    constraint_name: str,
) -> None:
    assert_rejected(migrated_database.config, sql, constraint_name)


def test_variant_image_must_belong_to_same_product(seeded_database: DatabaseConfig) -> None:
    assert_rejected(
        seeded_database,
        """
        INSERT INTO catalog.product_images (
            product_id, variant_id, storage_key, mime_type
        ) VALUES (
            '00000000-0000-7000-8000-000000000003',
            '00000000-0000-7000-8000-000000000012',
            'tests/cross-product.jpg',
            'image/jpeg'
        );
        """,
        "fk_product_images_variant_product",
    )


def test_duplicate_external_product_reference_is_rejected(
    seeded_database: DatabaseConfig,
) -> None:
    run_psql(
        seeded_database,
        sql="""
        INSERT INTO catalog.product_external_refs (
            product_id, source_system, external_product_id
        ) VALUES (
            '00000000-0000-7000-8000-000000000003', 'test-source', 'P-1'
        ) ON CONFLICT DO NOTHING;
        """,
    )
    assert_rejected(
        seeded_database,
        """
        INSERT INTO catalog.product_external_refs (
            product_id, source_system, external_product_id
        ) VALUES (
            '00000000-0000-7000-8000-000000000004', 'test-source', 'P-1'
        );
        """,
        "uq_product_external_refs_source_external",
    )


def test_duplicate_vendor_membership_is_rejected(seeded_database: DatabaseConfig) -> None:
    run_psql(
        seeded_database,
        sql="""
        INSERT INTO iam.vendor_memberships (vendor_id, user_id, role, status)
        VALUES (
            '00000000-0000-7000-8000-000000000002',
            '00000000-0000-7000-8000-000000000001',
            'owner',
            'active'
        ) ON CONFLICT DO NOTHING;
        """,
    )
    assert_rejected(
        seeded_database,
        """
        INSERT INTO iam.vendor_memberships (vendor_id, user_id, role, status)
        VALUES (
            '00000000-0000-7000-8000-000000000002',
            '00000000-0000-7000-8000-000000000001',
            'manager',
            'active'
        );
        """,
        "uq_vendor_memberships_vendor_user",
    )


def test_negative_price_is_rejected(seeded_database: DatabaseConfig) -> None:
    assert_rejected(
        seeded_database,
        """
        INSERT INTO catalog.listings (variant_id, price, status)
        VALUES (
            '00000000-0000-7000-8000-000000000011', -0.01, 'draft'
        );
        """,
        "ck_listings_price_non_negative",
    )


def test_negative_known_inventory_is_rejected(seeded_database: DatabaseConfig) -> None:
    assert_rejected(
        seeded_database,
        """
        INSERT INTO inventory.inventory_balances (
            listing_id, on_hand_quantity, reserved_quantity
        ) VALUES ('00000000-0000-7000-8000-000000000022', -1, 0);
        """,
        "ck_inventory_on_hand_non_negative",
    )


def test_reserved_inventory_cannot_exceed_known_on_hand(
    seeded_database: DatabaseConfig,
) -> None:
    assert_rejected(
        seeded_database,
        """
        INSERT INTO inventory.inventory_balances (
            listing_id, on_hand_quantity, reserved_quantity
        ) VALUES ('00000000-0000-7000-8000-000000000023', 2, 3);
        """,
        "ck_inventory_reserved_within_on_hand",
    )


def test_unknown_inventory_is_valid(seeded_database: DatabaseConfig) -> None:
    result = run_psql(
        seeded_database,
        sql="""
        INSERT INTO inventory.inventory_balances (
            listing_id, on_hand_quantity, reserved_quantity
        ) VALUES ('00000000-0000-7000-8000-000000000024', NULL, 0)
        ON CONFLICT (listing_id) DO UPDATE
        SET on_hand_quantity = EXCLUDED.on_hand_quantity,
            reserved_quantity = EXCLUDED.reserved_quantity
        RETURNING on_hand_quantity IS NULL;
        """,
    )
    assert result.stdout.splitlines()[0] == "t"


def test_confirmed_zero_inventory_is_distinct_from_unknown(
    seeded_database: DatabaseConfig,
) -> None:
    result = run_psql(
        seeded_database,
        sql="""
        INSERT INTO inventory.inventory_balances (
            listing_id, on_hand_quantity, reserved_quantity
        ) VALUES ('00000000-0000-7000-8000-000000000021', 0, 0)
        ON CONFLICT (listing_id) DO UPDATE
        SET on_hand_quantity = EXCLUDED.on_hand_quantity,
            reserved_quantity = EXCLUDED.reserved_quantity
        RETURNING on_hand_quantity, on_hand_quantity IS NULL;
        """,
    )
    assert result.stdout.splitlines()[0] == "0|f"


def test_only_one_unarchived_default_variant_per_product(
    seeded_database: DatabaseConfig,
) -> None:
    assert_rejected(
        seeded_database,
        """
        INSERT INTO catalog.product_variants (
            product_id, variant_code, status, is_default
        ) VALUES (
            '00000000-0000-7000-8000-000000000003',
            'second-default',
            'active',
            true
        );
        """,
        "uq_product_variants_default_active",
    )


def test_non_active_listing_allows_missing_khaadi_currency(
    seeded_database: DatabaseConfig,
) -> None:
    result = run_psql(
        seeded_database,
        sql="""
        INSERT INTO catalog.listings (variant_id, price, currency, status)
        VALUES (
            '00000000-0000-7000-8000-000000000012',
            4990.00,
            NULL,
            'draft'
        )
        RETURNING currency IS NULL;
        """,
    )
    assert result.stdout.splitlines()[0] == "t"


def test_active_listing_requires_complete_commercial_state(
    seeded_database: DatabaseConfig,
) -> None:
    assert_rejected(
        seeded_database,
        """
        INSERT INTO catalog.listings (
            variant_id, price, currency, availability, status
        ) VALUES (
            '00000000-0000-7000-8000-000000000012',
            4990.00,
            NULL,
            'in_stock',
            'active'
        );
        """,
        "ck_listings_active_commercial_state",
    )


def test_unknown_availability_value_is_rejected(seeded_database: DatabaseConfig) -> None:
    assert_rejected(
        seeded_database,
        """
        INSERT INTO catalog.listings (variant_id, availability, status)
        VALUES (
            '00000000-0000-7000-8000-000000000012', 'maybe', 'draft'
        );
        """,
        "ck_listings_availability",
    )


def test_product_has_no_listing_or_search_fields(migrated_database: MigratedDatabase) -> None:
    result = run_psql(
        migrated_database.config,
        sql="""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'catalog'
          AND table_name = 'products'
          AND column_name IN (
              'price', 'currency', 'availability', 'stock_quantity',
              'embedding', 'search_vector'
          )
        ORDER BY column_name;
        """,
    )
    assert result.stdout.strip() == ""


def test_forbidden_search_vector_and_commerce_infrastructure_absent(
    migrated_database: MigratedDatabase,
) -> None:
    forbidden = migrated_database.initial_report["forbidden_infrastructure"]
    assert forbidden == {
        "schemas": [],
        "tables": [],
        "tsvector_columns": [],
        "vector_extension": False,
    }


def test_audit_foreign_keys_cannot_cascade_delete_history(
    migrated_database: MigratedDatabase,
) -> None:
    constraints = migrated_database.initial_report["constraints"]
    audit_foreign_keys = [
        row
        for row in constraints  # type: ignore[union-attr]
        if row["schema_name"] == "audit" and row["constraint_type"] == "FOREIGN KEY"
    ]
    assert {row["constraint_name"] for row in audit_foreign_keys} == {
        "fk_audit_log_actor_user",
        "fk_audit_log_vendor",
    }
    assert all(row["delete_action"] == "SET NULL" for row in audit_foreign_keys)


def test_public_has_no_application_table_privileges(
    migrated_database: MigratedDatabase,
) -> None:
    result = run_psql(
        migrated_database.config,
        sql="""
        SELECT count(*)
        FROM information_schema.role_table_grants
        WHERE grantee = 'PUBLIC'
          AND table_schema IN ('iam', 'catalog', 'inventory', 'integration', 'audit');
        """,
    )
    assert result.stdout.strip() == "0"


def test_no_exact_duplicate_indexes(migrated_database: MigratedDatabase) -> None:
    result = run_psql(
        migrated_database.config,
        sql="""
        WITH indexes AS (
            SELECT
                index_row.indexrelid,
                index_row.indrelid,
                index_relation.relam,
                index_row.indisunique,
                index_row.indkey,
                index_row.indclass,
                index_row.indcollation,
                index_row.indoption,
                pg_get_expr(index_row.indexprs, index_row.indrelid) AS expressions,
                pg_get_expr(index_row.indpred, index_row.indrelid) AS predicate
            FROM pg_index AS index_row
            JOIN pg_class AS relation ON relation.oid = index_row.indrelid
            JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
            JOIN pg_class AS index_relation ON index_relation.oid = index_row.indexrelid
            WHERE namespace.nspname IN ('iam', 'catalog', 'inventory', 'integration', 'audit')
        )
        SELECT count(*)
        FROM indexes AS left_index
        JOIN indexes AS right_index
          ON left_index.indrelid = right_index.indrelid
         AND left_index.indexrelid < right_index.indexrelid
         AND left_index.relam = right_index.relam
         AND left_index.indisunique = right_index.indisunique
         AND left_index.indkey = right_index.indkey
         AND left_index.indclass = right_index.indclass
         AND left_index.indcollation = right_index.indcollation
         AND left_index.indoption = right_index.indoption
         AND left_index.expressions IS NOT DISTINCT FROM right_index.expressions
         AND left_index.predicate IS NOT DISTINCT FROM right_index.predicate;
        """,
    )
    assert result.stdout.strip() == "0"
