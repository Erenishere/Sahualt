from __future__ import annotations

import os
import re
from uuid import UUID, uuid4

import pytest

from sahulat_database.migrations import (
    DatabaseConfig,
    apply_migration,
    load_database_config,
    run_psql,
)
from sahulat_text.documents import DocumentContractError, build_product_documents
from sahulat_text.documents.artifacts import build_database_artifacts, verify_document_parity
from sahulat_text.documents.builder import serialize_documents
from sahulat_text.documents.repository import load_product_projections

pytestmark = pytest.mark.database


@pytest.fixture(scope="module")
def projection_database():
    if os.environ.get("RUN_DATABASE_TESTS") != "1":
        pytest.skip("set RUN_DATABASE_TESTS=1 to run PostgreSQL projection tests")
    base = load_database_config()
    database_name = f"sahulat_ai_document_test_{uuid4().hex[:12]}"
    assert re.fullmatch(r"sahulat_ai_document_test_[0-9a-f]{12}", database_name)
    admin = base.for_database("postgres")
    run_psql(admin, sql=f'CREATE DATABASE "{database_name}";')
    config = base.for_database(database_name)
    try:
        apply_migration(config)
        yield config
    finally:
        run_psql(admin, sql=f'DROP DATABASE "{database_name}" WITH (FORCE);')


@pytest.fixture
def semantic_product(projection_database):
    vendor, product, variant = uuid4(), uuid4(), uuid4()
    run_psql(
        projection_database,
        sql=f"""
        INSERT INTO catalog.vendors (id, display_name, slug)
            VALUES ('{vendor}', 'Synthetic Vendor', 'synthetic-{vendor.hex}');
        INSERT INTO catalog.products (id, vendor_id, name, description)
            VALUES ('{product}', '{vendor}', 'Canonical Shirt', 'Canonical description.');
        INSERT INTO catalog.product_variants (id, product_id, variant_code, color, is_default)
            VALUES ('{variant}', '{product}', 'default', 'Blue', true);
    """,
    )
    return projection_database, product, variant


def document_for(config: DatabaseConfig, product_id: UUID):
    projections = load_product_projections(config)
    return next(
        document
        for document in build_product_documents(projections)
        if document.product_id == product_id
    )


def test_loader_needs_no_listing_inventory_refs_or_images(semantic_product) -> None:
    config, product, _ = semantic_product
    document = document_for(config, product)
    assert document.name == "Canonical Shirt" and document.colors == ("Blue",)
    assert (
        document.text
        == "Product Name: Canonical Shirt\nDescription: Canonical description.\nColor: Blue"
    )


def test_multivariant_null_blank_unicode_archived_and_row_order(semantic_product) -> None:
    config, product, _ = semantic_product
    run_psql(
        config,
        stdin_sql=f"""
        INSERT INTO catalog.product_variants (product_id, variant_code, color, status, archived_at)
        VALUES ('{product}', 'black', 'black', 'active', NULL),
               ('{product}', 'red', '  Red', 'paused', NULL),
               ('{product}', 'duplicate', 'Ｂｌｕｅ', 'draft', NULL),
               ('{product}', 'unicode', 'سرخ', 'draft', NULL),
               ('{product}', 'unknown', NULL, 'draft', NULL),
               ('{product}', 'blank', E'\\t', 'draft', NULL),
               ('{product}', 'archived-status', 'Forbidden A', 'archived', NULL),
               ('{product}', 'archived-time', 'Forbidden B', 'draft', now());
    """,
    )
    before = document_for(config, product)
    assert before.colors == ("Blue", "Red", "black", "سرخ")
    # Force different heap row positions without changing semantic values.
    run_psql(
        config,
        sql=f"UPDATE catalog.product_variants SET updated_at = now() "
        f"WHERE product_id = '{product}';",
    )
    assert document_for(config, product) == before


@pytest.mark.parametrize("archive_rule", ["status = 'archived'", "archived_at = now()"])
def test_nonarchived_drafts_included_archived_products_excluded(
    semantic_product, archive_rule
) -> None:
    config, product, _ = semantic_product
    assert document_for(config, product).product_id == product
    run_psql(config, sql=f"UPDATE catalog.products SET {archive_rule} WHERE id = '{product}';")
    assert product not in {projection.product_id for projection in load_product_projections(config)}


def test_missing_color_is_valid(semantic_product) -> None:
    config, product, variant = semantic_product
    run_psql(
        config, sql=f"UPDATE catalog.product_variants SET color = NULL WHERE id = '{variant}';"
    )
    assert document_for(config, product).colors == ()
    assert "Color:" not in document_for(config, product).text


def test_color_addition_removal_and_equivalent_duplicate_checksum(semantic_product) -> None:
    config, product, _ = semantic_product
    before = document_for(config, product)
    run_psql(
        config,
        stdin_sql=f"""
        INSERT INTO catalog.product_variants (product_id, variant_code, color)
            VALUES ('{product}', 'equivalent', 'Ｂｌｕｅ');
    """,
    )
    assert document_for(config, product) == before
    run_psql(
        config,
        sql=f"""
        INSERT INTO catalog.product_variants (product_id, variant_code, color)
            VALUES ('{product}', 'new-color', 'Red');
    """,
    )
    assert document_for(config, product).document_checksum != before.document_checksum
    run_psql(
        config,
        sql=f"""
        UPDATE catalog.product_variants SET archived_at = now()
            WHERE product_id = '{product}' AND variant_code = 'new-color';
    """,
    )
    assert document_for(config, product) == before


@pytest.mark.parametrize(
    "dynamic_change",
    ["listing", "inventory", "image", "size", "timestamps", "external_ref", "brand_category"],
)
def test_dynamic_or_excluded_fields_do_not_affect_checksums(
    semantic_product, dynamic_change
) -> None:
    config, product, variant = semantic_product
    before = document_for(config, product)
    listing = uuid4()
    statements = {
        "listing": f"""
            INSERT INTO catalog.listings (id, variant_id, price, availability)
                VALUES ('{listing}', '{variant}', 1234.00, 'out_of_stock');
            UPDATE catalog.listings SET price = 4321, currency = 'USD',
                availability = 'in_stock', status = 'paused' WHERE id = '{listing}';
        """,
        "inventory": f"""
            INSERT INTO catalog.listings (id, variant_id) VALUES ('{listing}', '{variant}');
            INSERT INTO inventory.inventory_balances (listing_id, on_hand_quantity)
                VALUES ('{listing}', NULL);
            UPDATE inventory.inventory_balances SET on_hand_quantity = 99, reserved_quantity = 1
                WHERE listing_id = '{listing}';
        """,
        "image": f"""
            INSERT INTO catalog.product_images (product_id, storage_key, mime_type)
                VALUES ('{product}', 'synthetic/{product}/sentinel.jpg', 'image/jpeg');
            UPDATE catalog.product_images SET source_url = 'https://example.com/sentinel.jpg',
                sha256 = repeat('a', 64) WHERE product_id = '{product}';
        """,
        "size": f"""
            UPDATE catalog.product_variants SET size = 'SIZE-SENTINEL', sku = 'SKU-SENTINEL'
                WHERE id = '{variant}';
        """,
        "timestamps": f"""
            UPDATE catalog.products SET updated_at = now() + interval '1 day'
                WHERE id = '{product}';
        """,
        "external_ref": f"""
            INSERT INTO catalog.product_external_refs
                (product_id, source_system, external_product_id)
                VALUES ('{product}', 'synthetic', '{product}');
        """,
        "brand_category": f"""
            INSERT INTO catalog.categories (name, slug)
                VALUES ('CATEGORY-SENTINEL', 'synthetic-{product.hex}');
            UPDATE catalog.products SET brand_name = 'BRAND-SENTINEL',
                category_id = (SELECT id FROM catalog.categories
                    WHERE slug = 'synthetic-{product.hex}') WHERE id = '{product}';
        """,
    }
    run_psql(config, sql=statements[dynamic_change])
    assert document_for(config, product) == before
    assert "SENTINEL" not in document_for(config, product).text


@pytest.mark.parametrize("field", ["name", "description", "color"])
def test_database_semantic_edits_change_checksums(semantic_product, field) -> None:
    config, product, variant = semantic_product
    before = document_for(config, product)
    table, identity = ("product_variants", variant) if field == "color" else ("products", product)
    run_psql(
        config,
        sql=f"UPDATE catalog.{table} SET {field} = 'Changed semantic value' "
        f"WHERE id = '{identity}';",
    )
    assert document_for(config, product).document_checksum != before.document_checksum


def test_malformed_required_canonical_state_aborts_without_artifacts(
    semantic_product, tmp_path
) -> None:
    config, product, _ = semantic_product
    # btrim's SQL space check alone permits tabs; the builder must still reject empty semantics.
    run_psql(config, sql=f"UPDATE catalog.products SET name = E'\\t' WHERE id = '{product}';")
    try:
        with pytest.raises(DocumentContractError):
            build_database_artifacts(
                config, output_directory=tmp_path / "documents", report_path=tmp_path / "report.md"
            )
        assert not (tmp_path / "documents").exists()
    finally:
        run_psql(
            config,
            sql=f"UPDATE catalog.products SET name = 'Canonical Shirt' WHERE id = '{product}';",
        )


def test_two_live_loads_and_artifact_builds_are_identical(semantic_product, tmp_path) -> None:
    config, _, _ = semantic_product
    first_sources = load_product_projections(config)
    second_sources = load_product_projections(config)
    first_docs = build_product_documents(first_sources)
    assert serialize_documents(first_docs) == serialize_documents(
        build_product_documents(second_sources)
    )
    assert verify_document_parity(first_sources, first_docs)["status"] == "GREEN"
    directory = tmp_path / "documents"
    first = build_database_artifacts(
        config, output_directory=directory, report_path=tmp_path / "report.md"
    )
    original_jsonl = (directory / "product-text-v1.jsonl").read_bytes()
    original_manifest = (directory / "product-text-v1.manifest.json").read_bytes()
    second = build_database_artifacts(
        config, output_directory=directory, report_path=tmp_path / "report.md"
    )
    assert first["manifest"] == second["manifest"]
    assert (directory / "product-text-v1.jsonl").read_bytes() == original_jsonl
    assert (directory / "product-text-v1.manifest.json").read_bytes() == original_manifest
    assert not any(second["forbidden_infrastructure"].values())
