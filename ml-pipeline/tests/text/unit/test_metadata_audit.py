import csv
from pathlib import Path

import pytest

from sahulat_text.metadata_audit import (
    MetadataAuditError,
    audit_product_metadata,
    normalize_text,
    render_markdown,
    write_audit_artifacts,
)

pytestmark = pytest.mark.unit

HEADERS = [
    "ID",
    "Product Name",
    "Product Description",
    "Price",
    "Availability",
    "Color",
    "Img Path",
    "Product Link",
]


def write_fixture(path: Path, rows: list[list[str]], headers: list[str] = HEADERS) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(headers)
        writer.writerows(rows)


def audit_fixture(path: Path):
    return audit_product_metadata(path, source_path="tests/fixtures/products.csv")


def valid_row(product_id: str = "P1") -> list[str]:
    return [
        product_id,
        "Blue Shirt",
        "A sufficiently detailed product description",
        "4990",
        "In Stock",
        "Blue",
        f"images/{product_id}",
        f"https://example.test/{product_id}",
    ]


def test_missing_and_blank_semantic_fields_are_reported(tmp_path: Path) -> None:
    path = tmp_path / "products.csv"
    rows = [valid_row("P1"), valid_row("")]
    rows[0][1] = "   "
    rows[1][2] = ""
    write_fixture(path, rows)

    audit = audit_fixture(path)

    assert audit["field_statistics"]["Product Name"]["whitespace_only_count"] == 1
    assert audit["field_statistics"]["Product Description"]["blank_string_count"] == 1
    assert audit["exclusions_and_quarantine"]["quarantined_product_id_count"] == 1
    assert audit["exclusions_and_quarantine"]["rows_without_product_id_count"] == 1


def test_short_description_requires_validation_but_remains_a_candidate(tmp_path: Path) -> None:
    path = tmp_path / "products.csv"
    row = valid_row("P1")
    row[2] = "Short"
    write_fixture(path, [row])

    audit = audit_fixture(path)
    readiness = {
        item["field"]: item["readiness"]
        for item in audit["contract_fitness"]["field_classifications"]
    }

    assert readiness["Product Description"] == "REQUIRES VALIDATION"
    assert audit["exclusions_and_quarantine"]["valid_canonical_document_candidate_count"] == 1


def test_missing_required_column_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "products.csv"
    headers = [header for header in HEADERS if header != "Product Description"]
    write_fixture(path, [["P1"] * len(headers)], headers)

    with pytest.raises(MetadataAuditError, match="missing required columns"):
        audit_fixture(path)


def test_identical_and_conflicting_duplicate_ids_are_distinguished(tmp_path: Path) -> None:
    path = tmp_path / "products.csv"
    identical = valid_row("P1")
    conflict_a = valid_row("P2")
    conflict_b = valid_row("P2")
    conflict_b[1] = "Red Shirt"
    write_fixture(path, [identical, identical, conflict_a, conflict_b])

    integrity = audit_fixture(path)["product_id_integrity"]

    assert integrity["duplicate_id_group_count"] == 2
    assert integrity["identical_duplicate_group_count"] == 1
    assert integrity["conflicting_duplicate_group_count"] == 1
    assert integrity["conflicting_duplicate_product_ids"] == ["P2"]
    assert integrity["conflicting_duplicate_groups"][0]["records"][0]["source_line_start"] == 4
    assert (
        integrity["conflicting_duplicate_groups"][0]["conflicting_fields"][0]["field"]
        == "Product Name"
    )


def test_malformed_prices_and_unknown_availability_are_evidence(tmp_path: Path) -> None:
    path = tmp_path / "products.csv"
    malformed = valid_row("P1")
    malformed[3] = "PKR 4,990"
    malformed[4] = "Coming Soon"
    negative = valid_row("P2")
    negative[3] = "-1"
    write_fixture(path, [malformed, negative])

    audit = audit_fixture(path)

    assert audit["price_analysis"]["parse_failure_count"] == 1
    assert audit["price_analysis"]["negative_value_count"] == 1
    assert audit["availability_analysis"]["unmapped_values"] == ["Coming Soon"]
    readiness = {
        item["field"]: item["readiness"]
        for item in audit["contract_fitness"]["field_classifications"]
    }
    assert readiness["Price"] == "REQUIRES VALIDATION"
    assert readiness["Availability"] == "REQUIRES VALIDATION"


def test_unicode_control_and_whitespace_normalization() -> None:
    assert normalize_text("  Blue\t\u212b  Shirt\x00 ") == "Blue Å Shirt"


def test_malformed_csv_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "products.csv"
    path.write_text(",".join(HEADERS) + '\nP1,"unterminated', encoding="utf-8")

    with pytest.raises(MetadataAuditError, match="malformed"):
        audit_fixture(path)


def test_audit_and_artifacts_are_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "products.csv"
    write_fixture(path, [valid_row()])

    first = audit_fixture(path)
    second = audit_fixture(path)
    assert first == second
    assert render_markdown(first) == render_markdown(second)

    first_json = tmp_path / "first.json"
    first_report = tmp_path / "first.md"
    second_json = tmp_path / "second.json"
    second_report = tmp_path / "second.md"
    write_audit_artifacts(first, first_json, first_report)
    write_audit_artifacts(second, second_json, second_report)
    assert first_json.read_bytes() == second_json.read_bytes()
    assert first_report.read_bytes() == second_report.read_bytes()


def test_color_maps_to_product_variant_without_inference(tmp_path: Path) -> None:
    path = tmp_path / "products.csv"
    write_fixture(path, [valid_row()])

    audit = audit_fixture(path)
    mapping = {item["source_field"]: item for item in audit["source_to_contract_mapping"]}

    assert mapping["Color"]["production_owner"] == "ProductVariant"
    assert audit["contract"]["fixture_variant_policy"] == {
        "variants_per_product": 1,
        "variant_code": "default",
        "color_source": "Color",
        "size": None,
        "inference_performed": False,
    }
    assert "Size" in audit["contract_fitness"]["absent_production_fields"]
