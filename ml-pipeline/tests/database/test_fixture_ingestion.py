from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import replace
from decimal import Decimal

import pytest

from sahulat_database.migrations import (
    DatabaseConfig,
    apply_migration,
    load_database_config,
    run_psql,
)
from sahulat_text.ingestion.canonical import content_checksum, semantic_checksum, vendor_uuid
from sahulat_text.ingestion.contracts import (
    CanonicalImageInput,
    CanonicalImportBatch,
    CanonicalListingInput,
    CanonicalProductInput,
    CanonicalVariantInput,
    IngestionContractError,
)
from sahulat_text.ingestion.khaadi.mapper import map_khaadi_fixture
from sahulat_text.ingestion.khaadi.reader import load_khaadi_authority
from sahulat_text.ingestion.postgres import (
    CanonicalImportError,
    import_canonical_batch,
    verify_batch_parity,
)

pytestmark = pytest.mark.database


@pytest.fixture(scope="module")
def ingestion_database() -> DatabaseConfig:
    if os.environ.get("RUN_DATABASE_TESTS") != "1":
        pytest.skip("set RUN_DATABASE_TESTS=1 to run PostgreSQL ingestion tests")
    try:
        base_config = load_database_config()
    except (FileNotFoundError, ValueError) as error:
        pytest.skip(str(error))

    database_name = f"sahulat_ai_ingest_test_{uuid.uuid4().hex[:12]}"
    assert re.fullmatch(r"[a-z0-9_]+", database_name)
    admin_config = base_config.for_database("postgres")
    run_psql(admin_config, sql=f'CREATE DATABASE "{database_name}";')
    config = base_config.for_database(database_name)
    try:
        apply_migration(config)
        yield config
    finally:
        run_psql(
            admin_config,
            sql=f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE);',
        )


def canonical_product(
    source: str,
    product_id: str,
    *,
    name: str = "Synthetic Product",
    color: str | None = None,
    images: tuple[CanonicalImageInput, ...] = (),
) -> CanonicalProductInput:
    listing = CanonicalListingInput(
        price=Decimal("1000.00"),
        currency=None,
        availability="in_stock",
        status="draft",
    )
    variant = CanonicalVariantInput(
        variant_code="default",
        color=color,
        size=None,
        sku=None,
        status="draft",
        is_default=True,
        listing=listing,
    )
    return CanonicalProductInput(
        external_source=source,
        external_product_id=product_id,
        source_checksum=content_checksum({"source": source, "id": product_id, "name": name}),
        name=name,
        description="Synthetic fixture description",
        variants=(variant,),
        images=images,
        brand_name=None,
        category_id=None,
        status="draft",
    )


def canonical_batch(
    source: str,
    *,
    product: CanonicalProductInput | None = None,
) -> CanonicalImportBatch:
    selected_product = product or canonical_product(source, "P-1")
    return CanonicalImportBatch(
        importer_version="synthetic-test-v1",
        external_source=source,
        vendor_display_name=f"Fixture {source}",
        vendor_slug=f"fixture-{source}",
        products=(selected_product,),
    )


def test_clean_product_import_into_fresh_migration(ingestion_database: DatabaseConfig) -> None:
    batch = canonical_batch("synthetic-clean")
    execution = import_canonical_batch(ingestion_database, batch)
    parity = verify_batch_parity(ingestion_database, batch)

    assert execution.created == {
        "image_external_refs": 0,
        "images": 0,
        "inventory": 0,
        "listings": 1,
        "outbox_events": 0,
        "product_external_refs": 1,
        "products": 1,
        "variants": 1,
        "vendors": 1,
    }
    assert parity["status"] == "GREEN"
    assert parity["semantic_checksum"] == semantic_checksum(batch)


def test_product_variant_listing_relationships_are_canonical(
    ingestion_database: DatabaseConfig,
) -> None:
    result = run_psql(
        ingestion_database,
        sql="""
        SELECT count(*)
        FROM catalog.product_external_refs AS ref
        JOIN catalog.products AS product ON product.id = ref.product_id
        JOIN catalog.product_variants AS variant ON variant.product_id = product.id
        JOIN catalog.listings AS listing ON listing.variant_id = variant.id
        WHERE ref.source_system = 'synthetic-clean'
          AND variant.variant_code = 'default'
          AND variant.is_default
          AND product.status = 'draft'
          AND listing.status = 'draft';
        """,
    )
    assert result.stdout.strip() == "1"


def test_unsupported_fields_and_inventory_remain_absent(
    ingestion_database: DatabaseConfig,
) -> None:
    result = run_psql(
        ingestion_database,
        sql="""
        SELECT jsonb_build_object(
            'brand_null', product.brand_name IS NULL,
            'category_null', product.category_id IS NULL,
            'size_null', variant.size IS NULL,
            'currency_null', listing.currency IS NULL,
            'inventory_absent', balance.listing_id IS NULL
        )
        FROM catalog.product_external_refs AS ref
        JOIN catalog.products AS product ON product.id = ref.product_id
        JOIN catalog.product_variants AS variant ON variant.product_id = product.id
        JOIN catalog.listings AS listing ON listing.variant_id = variant.id
        LEFT JOIN inventory.inventory_balances AS balance ON balance.listing_id = listing.id
        WHERE ref.source_system = 'synthetic-clean';
        """,
    )
    assert all(json.loads(result.stdout).values())


def test_fixture_vendor_and_default_variant_are_created_once(
    ingestion_database: DatabaseConfig,
) -> None:
    batch = canonical_batch("synthetic-idempotent")
    first = import_canonical_batch(ingestion_database, batch)
    second = import_canonical_batch(ingestion_database, batch)
    vendor_id = vendor_uuid(batch.external_source)
    counts = run_psql(
        ingestion_database,
        sql=f"""
        SELECT
            (SELECT count(*) FROM catalog.vendors WHERE id = '{vendor_id}') || '|' ||
            (SELECT count(*)
             FROM catalog.product_variants AS variant
             JOIN catalog.product_external_refs AS ref ON ref.product_id = variant.product_id
             WHERE ref.source_system = 'synthetic-idempotent' AND variant.is_default);
        """,
    )

    assert first.created["products"] == 1
    assert second.is_no_op
    assert counts.stdout.strip() == "1|1"


def test_conflicting_existing_fixture_state_fails_without_overwrite(
    ingestion_database: DatabaseConfig,
) -> None:
    source = "synthetic-conflict"
    batch = canonical_batch(source)
    import_canonical_batch(ingestion_database, batch)
    changed_product = replace(
        batch.products[0],
        name="Unexpected Rewrite",
        source_checksum="f" * 64,
    )
    changed_batch = replace(batch, products=(changed_product,))

    with pytest.raises(CanonicalImportError, match="rolled back"):
        import_canonical_batch(ingestion_database, changed_batch)

    name = run_psql(
        ingestion_database,
        sql="""
        SELECT product.name
        FROM catalog.products AS product
        JOIN catalog.product_external_refs AS ref ON ref.product_id = product.id
        WHERE ref.source_system = 'synthetic-conflict';
        """,
    )
    assert name.stdout.strip() == "Synthetic Product"


def test_child_insert_failure_rolls_back_entire_product(
    ingestion_database: DatabaseConfig,
) -> None:
    source = "synthetic-rollback"
    images = (
        CanonicalImageInput(
            "P-1/image-1.jpg",
            "fixtures/duplicate-storage-key.jpg",
            "images/P-1/image-1.jpg",
            "image/jpeg",
            "a" * 64,
            10,
            10,
            0,
            True,
        ),
        CanonicalImageInput(
            "P-1/image-2.jpg",
            "fixtures/duplicate-storage-key.jpg",
            "images/P-1/image-2.jpg",
            "image/jpeg",
            "b" * 64,
            10,
            10,
            1,
            False,
        ),
    )
    batch = canonical_batch(
        source,
        product=canonical_product(source, "P-1", images=images),
    )

    with pytest.raises(CanonicalImportError, match="rolled back"):
        import_canonical_batch(ingestion_database, batch)

    counts = run_psql(
        ingestion_database,
        sql=f"""
        SELECT
            (SELECT count(*) FROM catalog.vendors WHERE id = '{vendor_uuid(source)}') || '|' ||
            (SELECT count(*) FROM catalog.product_external_refs
             WHERE source_system = 'synthetic-rollback');
        """,
    )
    assert counts.stdout.strip() == "0|0"


def test_malformed_required_product_never_reaches_database(
    ingestion_database: DatabaseConfig,
) -> None:
    source = "synthetic-malformed"
    with pytest.raises(IngestionContractError):
        canonical_product(source, "P-1", name="")
    count = run_psql(
        ingestion_database,
        sql="""
        SELECT count(*) FROM catalog.product_external_refs
        WHERE source_system = 'synthetic-malformed';
        """,
    )
    assert count.stdout.strip() == "0"


def test_import_emits_no_outbox_events(ingestion_database: DatabaseConfig) -> None:
    before = run_psql(ingestion_database, sql="SELECT count(*) FROM integration.outbox_events;")
    import_canonical_batch(ingestion_database, canonical_batch("synthetic-no-outbox"))
    after = run_psql(ingestion_database, sql="SELECT count(*) FROM integration.outbox_events;")
    assert before.stdout.strip() == after.stdout.strip() == "0"


def test_import_does_not_create_search_fts_vector_or_commerce(
    ingestion_database: DatabaseConfig,
) -> None:
    result = run_psql(
        ingestion_database,
        sql="""
        SELECT jsonb_build_object(
            'search', to_regnamespace('search') IS NOT NULL,
            'commerce', to_regnamespace('commerce') IS NOT NULL,
            'vector', EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector'),
            'tsvector', EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE udt_name = 'tsvector'
                  AND table_schema NOT IN ('pg_catalog', 'information_schema')
            )
        );
        """,
    )
    assert not any(json.loads(result.stdout).values())


def test_audited_khaadi_fixture_imports_into_fresh_migration(
    ingestion_database: DatabaseConfig,
) -> None:
    mapping = map_khaadi_fixture(load_khaadi_authority(verify_image_binaries=False))
    first = import_canonical_batch(ingestion_database, mapping.batch)
    parity = verify_batch_parity(ingestion_database, mapping.batch)
    second = import_canonical_batch(ingestion_database, mapping.batch)

    assert first.created["products"] == 400
    assert first.created["variants"] == 400
    assert first.created["listings"] == 400
    assert first.created["images"] == 2093
    assert parity["status"] == "GREEN"
    assert parity["counts"]["inventory"] == 0
    assert second.is_no_op
