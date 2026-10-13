from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

import sahulat_text.ingestion.khaadi.reader as khaadi_reader
from sahulat_text.ingestion.canonical import (
    fixture_uuid,
    semantic_checksum,
    semantic_projection,
)
from sahulat_text.ingestion.contracts import (
    CanonicalImageInput,
    CanonicalImportBatch,
    CanonicalListingInput,
    CanonicalProductInput,
    CanonicalVariantInput,
    IngestionContractError,
    normalize_ingestion_text,
)
from sahulat_text.ingestion.khaadi.mapper import (
    FIXTURE_VENDOR_NAME,
    FIXTURE_VENDOR_SLUG,
    IMPORTER_VERSION,
    KhaadiMappingError,
    map_khaadi_fixture,
)
from sahulat_text.ingestion.khaadi.reader import (
    EXPECTED_GATE1_VERSION,
    EXPECTED_SOURCE_SHA256,
    EXPECTED_SOURCE_SYSTEM,
    KhaadiAuthority,
    KhaadiAuthorityError,
    load_khaadi_authority,
)

pytestmark = pytest.mark.unit


def source_row(
    product_id: str = "SYN-1",
    *,
    name: str = "Synthetic Product",
    description: str = "Synthetic description",
    color: str = "BLUE",
    availability: str = "In Stock",
    price: str = "1000",
) -> dict[str, str]:
    return {
        "ID": product_id,
        "Product Name": name,
        "Product Description": description,
        "Price": price,
        "Availability": availability,
        "Color": color,
        "Img Path": f"images\\{product_id}",
        "Product Link": "https://example.invalid/product",
    }


def authority_for(
    rows: tuple[dict[str, str], ...],
    *,
    valid_ids: frozenset[str],
    quarantined: tuple[dict[str, object], ...] = (),
    images: tuple[dict[str, object], ...] = (),
) -> KhaadiAuthority:
    return KhaadiAuthority(
        audit={"audit_version": EXPECTED_GATE1_VERSION, "evidence_sha256": "synthetic"},
        source_metadata={"dataset_version": "synthetic"},
        rows=rows,
        visual_retained=images,
        visual_excluded=(),
        source_path=Path("synthetic.csv"),
        source_path_record="synthetic.csv",
        source_sha256="0" * 64,
        manifest_path=Path("synthetic-manifest.json"),
        manifest_path_record="synthetic-manifest.json",
        manifest_sha256="1" * 64,
        visual_audit_sha256="2" * 64,
        dataset_version="synthetic",
        valid_product_ids=valid_ids,
        quarantined_products=quarantined,
    )


def mapped_batch(row: dict[str, str] | None = None) -> CanonicalImportBatch:
    selected = row or source_row()
    return map_khaadi_fixture(
        authority_for((selected,), valid_ids=frozenset({selected["ID"]}))
    ).batch


def test_clean_khaadi_row_maps_to_canonical_contract() -> None:
    product = mapped_batch().products[0]
    variant = product.variants[0]

    assert product.name == "Synthetic Product"
    assert product.description == "Synthetic description"
    assert product.brand_name is None
    assert product.category_id is None
    assert variant.color == "BLUE"
    assert variant.size is None
    assert variant.is_default is True
    assert variant.listing.price == Decimal("1000")
    assert variant.listing.currency is None
    assert variant.listing.availability == "in_stock"
    assert variant.listing.status == "draft"


def test_missing_optional_color_remains_none() -> None:
    variant = mapped_batch(source_row(color="")).products[0].variants[0]
    assert variant.color is None


def test_khaadi_images_remain_product_level_and_deterministically_ordered() -> None:
    row = source_row()
    images = (
        {
            "image_id": "SYN-1/image_1.jpg",
            "product_id": "SYN-1",
            "image_path": "Khaadi_Data/images/SYN-1/image_1.jpg",
            "binary_sha256": "b" * 64,
            "width": 800,
            "height": 1200,
        },
        {
            "image_id": "SYN-1/image_0.jpg",
            "product_id": "SYN-1",
            "image_path": "Khaadi_Data/images/SYN-1/image_0.jpg",
            "binary_sha256": "a" * 64,
            "width": 800,
            "height": 1200,
        },
    )
    product = map_khaadi_fixture(
        authority_for((row,), valid_ids=frozenset({"SYN-1"}), images=images)
    ).batch.products[0]

    assert [image.external_image_id for image in product.images] == [
        "SYN-1/image_0.jpg",
        "SYN-1/image_1.jpg",
    ]
    assert [image.sort_order for image in product.images] == [0, 1]
    assert [image.is_primary for image in product.images] == [True, False]
    assert all(image.variant_code is None for image in product.images)


def test_gate1_quarantined_row_is_not_imported() -> None:
    valid = source_row("VALID-1")
    quarantined = source_row("QUARANTINE-1")
    result = map_khaadi_fixture(
        authority_for(
            (valid, quarantined),
            valid_ids=frozenset({"VALID-1"}),
            quarantined=({"product_id": "QUARANTINE-1", "reason": "conflicting-duplicate-id"},),
        )
    )

    assert [product.external_product_id for product in result.batch.products] == ["VALID-1"]
    assert len(result.quarantined_products) == 1


def test_unknown_availability_is_not_silently_inferred() -> None:
    with pytest.raises(KhaadiMappingError, match="no longer map cleanly"):
        mapped_batch(source_row(availability="Sometimes"))


@pytest.mark.parametrize(
    ("field", "value"),
    [("Product Name", ""), ("Product Description", ""), ("ID", "")],
)
def test_malformed_required_semantics_are_rejected(field: str, value: str) -> None:
    row = source_row()
    row[field] = value
    valid_id = row["ID"]
    with pytest.raises(KhaadiMappingError):
        map_khaadi_fixture(authority_for((row,), valid_ids=frozenset({valid_id})))


def test_active_listing_without_currency_is_rejected_by_canonical_contract() -> None:
    with pytest.raises(IngestionContractError, match="active listing requires"):
        CanonicalListingInput(
            price=Decimal("1000.00"),
            currency=None,
            availability="in_stock",
            status="active",
        )


def test_canonical_product_requires_exactly_one_default_variant() -> None:
    listing = CanonicalListingInput(Decimal("1.00"), None, "in_stock", "draft")
    variant = CanonicalVariantInput("default", None, None, False, listing)
    with pytest.raises(IngestionContractError, match="exactly one default"):
        CanonicalProductInput(
            EXPECTED_SOURCE_SYSTEM,
            "SYN-1",
            "a" * 64,
            "Name",
            "Description",
            (variant,),
        )


def test_duplicate_external_product_id_is_rejected_before_database_write() -> None:
    product = mapped_batch().products[0]
    with pytest.raises(IngestionContractError, match="external product IDs"):
        CanonicalImportBatch(
            IMPORTER_VERSION,
            EXPECTED_SOURCE_SYSTEM,
            FIXTURE_VENDOR_NAME,
            FIXTURE_VENDOR_SLUG,
            (product, product),
        )


def test_semantic_checksum_is_deterministic_and_order_independent() -> None:
    first = mapped_batch(source_row("SYN-1"))
    second_product = mapped_batch(source_row("SYN-2")).products[0]
    combined_a = replace(first, products=(first.products[0], second_product))
    combined_b = replace(first, products=(second_product, first.products[0]))

    assert semantic_checksum(combined_a) == semantic_checksum(combined_b)
    assert semantic_projection(combined_a) == semantic_projection(combined_b)


def test_generated_timestamps_cannot_affect_semantic_checksum() -> None:
    batch = mapped_batch()
    projection = semantic_projection(batch)

    assert "created_at" not in repr(projection)
    assert "updated_at" not in repr(projection)
    assert semantic_checksum(batch) == semantic_checksum(replace(batch))


def test_fixture_uuid_is_deterministic_and_namespaced() -> None:
    first = fixture_uuid("khaadi-v1", "product", "SYN-1")
    assert first == fixture_uuid("khaadi-v1", "product", "SYN-1")
    assert first != fixture_uuid("khaadi-v1", "variant", "SYN-1")
    assert first.version == 5


def test_ingestion_normalization_matches_locked_nfkc_whitespace_policy() -> None:
    assert normalize_ingestion_text("  Blue\t\u212b  ") == "Blue Å"


def test_frozen_khaadi_authority_matches_gate1() -> None:
    authority = load_khaadi_authority(verify_image_binaries=False)
    assert authority.source_sha256 == EXPECTED_SOURCE_SHA256
    assert authority.audit["audit_version"] == EXPECTED_GATE1_VERSION
    assert len(authority.rows) == 400
    assert len(authority.valid_product_ids) == 400
    assert not authority.quarantined_products
    assert len(authority.visual_retained) == 2093
    assert len(authority.visual_excluded) == 16


def test_actual_khaadi_mapping_respects_gate1_counts() -> None:
    mapping = map_khaadi_fixture(load_khaadi_authority(verify_image_binaries=False))
    assert mapping.source_products == 400
    assert len(mapping.batch.products) == 400
    assert sum(len(product.variants) for product in mapping.batch.products) == 400
    assert sum(len(product.images) for product in mapping.batch.products) == 2093
    assert not mapping.rejected_products
    assert not mapping.quarantined_products


def test_source_checksum_drift_blocks_normal_import(monkeypatch: pytest.MonkeyPatch) -> None:
    original = khaadi_reader._file_sha256

    def drift_csv_only(path: Path) -> str:
        return "f" * 64 if path.name == "khaadi_data.csv" else original(path)

    monkeypatch.setattr(khaadi_reader, "_file_sha256", drift_csv_only)
    with pytest.raises(KhaadiAuthorityError, match="source checksum differs"):
        load_khaadi_authority(verify_image_binaries=False)


def test_canonical_image_rejects_machine_absolute_source_path() -> None:
    with pytest.raises(IngestionContractError, match="repository-portable"):
        CanonicalImageInput(
            external_image_id="image.jpg",
            storage_key="fixtures/image.jpg",
            source_path=r"C:\fixture\image.jpg",
            mime_type="image/jpeg",
            sha256="a" * 64,
            width=1,
            height=1,
            sort_order=0,
            is_primary=True,
        )
