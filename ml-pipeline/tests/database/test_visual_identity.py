from uuid import UUID

import pytest

from sahulat_api.catalogue import load_external_image_references
from sahulat_api.identity import resolve_canonical_matches
from sahulat_text.ingestion.contracts import CanonicalImageInput, CanonicalImportBatch
from sahulat_text.ingestion.postgres import import_canonical_batch
from sahulat_visual.domain import ProductMatch
from tests.database.test_fixture_ingestion import canonical_product, ingestion_database

registered_fixture = ingestion_database
pytestmark = pytest.mark.database


def test_canonical_resolution_from_actual_schema(ingestion_database):
    source = "synthetic-visual-v1"
    image = CanonicalImageInput(
        external_image_id="A-1",
        source_path="synthetic/a.png",
        storage_key="synthetic/a.png",
        mime_type="image/png",
        sha256="a" * 64,
        width=32,
        height=32,
        sort_order=0,
        is_primary=True,
        variant_code="default",
    )
    product = canonical_product(source, "A", images=(image,))
    batch = CanonicalImportBatch(
        importer_version="synthetic-http-test-v1",
        external_source=source,
        vendor_display_name="Synthetic Visual Fixture",
        vendor_slug="synthetic-visual-fixture",
        products=(product,),
    )
    import_canonical_batch(ingestion_database, batch)
    refs = load_external_image_references(ingestion_database, source)
    assert len(refs) == 1
    resolved = resolve_canonical_matches(
        source, [ProductMatch("A", 0.9, "A-1", "private/path")], refs
    )
    assert isinstance(resolved[0].product_id, UUID)
    assert resolved[0].product_id == refs[0].product_id
    assert resolved[0].matched_image_id == refs[0].image_id
    assert resolved[0].score == 0.9
    assert "path" not in repr(refs)


def test_other_source_does_not_resolve(ingestion_database):
    assert load_external_image_references(ingestion_database, "unknown-source-v1") == ()


def test_reference_projection_rejects_sql_injection(ingestion_database):
    with pytest.raises(ValueError):
        load_external_image_references(ingestion_database, "bad'; DROP SCHEMA catalog; --")
