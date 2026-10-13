from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from uuid import UUID

import pytest

from sahulat_database.migrations import DatabaseConfig
from sahulat_text.documents import (
    CanonicalProductProjection,
    DocumentContractError,
    build_product_document,
    build_product_documents,
)
from sahulat_text.documents.artifacts import (
    render_build_report,
    verify_document_parity,
    verify_jsonl_artifact,
)
from sahulat_text.documents.builder import serialize_documents
from sahulat_text.documents.repository import PROJECTION_SQL
from sahulat_text.documents.serialization import canonical_json_bytes, sha256
from sahulat_text.normalization import normalize_text

PRODUCT_ID = UUID("019a0000-0000-7000-8000-000000000001")


def projection(**changes) -> CanonicalProductProjection:
    return replace(
        CanonicalProductProjection(PRODUCT_ID, "Lawn Shirt", "Original description.", ("Blue",)),
        **changes,
    )


def test_khaadi_independence_and_exact_contract() -> None:
    document = build_product_document(projection())
    assert document.record() == {
        "schema_version": "product-text-v1",
        "product_id": str(PRODUCT_ID),
        "fields": {
            "name": "Lawn Shirt",
            "description": "Original description.",
            "colors": ["Blue"],
        },
        "text": "Product Name: Lawn Shirt\nDescription: Original description.\nColor: Blue",
        "document_checksum": sha256(canonical_json_bytes(document.payload())),
    }
    assert str(PRODUCT_ID) not in document.text


def test_projection_and_document_are_immutable() -> None:
    source = projection()
    with pytest.raises(FrozenInstanceError):
        source.name = "changed"
    document = build_product_document(source)
    with pytest.raises(FrozenInstanceError):
        document.text = "changed"


@pytest.mark.parametrize("colors", [(), ("",), (" \t\n",)])
def test_optional_missing_color_omits_line(colors) -> None:
    document = build_product_document(projection(colors=colors))
    assert document.colors == ()
    assert document.text == "Product Name: Lawn Shirt\nDescription: Original description."
    assert document.record()["fields"]["colors"] == []


@pytest.mark.parametrize("field", ["name", "description"])
@pytest.mark.parametrize("value", [None, "", " \t\n", "\x00\x01"])
def test_required_fields_rejected_without_placeholder(field, value) -> None:
    with pytest.raises(DocumentContractError):
        build_product_document(projection(**{field: value}))


@pytest.mark.parametrize("identity", [None, "P-1", UUID(int=0)])
def test_invalid_identity_rejected(identity) -> None:
    with pytest.raises(DocumentContractError):
        projection(product_id=identity)


@pytest.mark.parametrize("colors", [["Blue"], (None,), (1,)])
def test_projection_has_strict_immutable_color_type(colors) -> None:
    with pytest.raises(DocumentContractError):
        projection(colors=colors)


def test_unicode_whitespace_controls_language_and_case() -> None:
    document = build_product_document(
        projection(
            name="  Ｌａｗｎ\tShirt  ",
            description="اردو\x00中文  café!\nOriginal-case.",
            colors=("Ｂｌｕｅ", "Blue", "  Red", "black", "سرخ", "藍", ""),
        )
    )
    assert document.name == "Lawn Shirt"
    assert document.description == "اردو 中文 café! Original-case."
    assert document.colors == ("Blue", "Red", "black", "سرخ", "藍")
    assert not document.text.endswith("\n")


def test_multi_variant_order_deduplication_and_case_are_deterministic() -> None:
    first = build_product_document(
        projection(colors=("Blue", "black", "Blue", "  Red", "Ｂｌｕｅ"))
    )
    second = build_product_document(projection(colors=("Red", "black", "Blue")))
    assert first == second
    assert first.colors == ("Blue", "Red", "black")
    assert first.text.endswith("Color: Blue, Red, black")
    assert build_product_document(projection(colors=("Blue", "blue"))).colors == ("Blue", "blue")


def test_free_text_colors_are_not_split_or_rewritten() -> None:
    assert build_product_document(projection(colors=("Blue / White",))).colors == ("Blue / White",)


def test_malformed_unicode_is_rejected() -> None:
    with pytest.raises(DocumentContractError, match="Unicode"):
        build_product_document(projection(description="unpaired \ud800 surrogate"))


@pytest.mark.parametrize(
    "change",
    [
        {"name": "Different name"},
        {"description": "Different description"},
        {"colors": ("Red",)},
    ],
)
def test_semantic_change_changes_checksum(change) -> None:
    assert build_product_document(projection(**change)).document_checksum != (
        build_product_document(projection()).document_checksum
    )


def test_same_projection_same_record_and_checksum() -> None:
    assert build_product_document(projection()) == build_product_document(projection())


def test_batch_and_artifact_order_are_deterministic(tmp_path) -> None:
    sources = [projection(), projection(product_id=UUID(int=1), colors=())]
    first = build_product_documents(sources)
    second = build_product_documents(reversed(sources))
    assert first == second
    assert serialize_documents(first) == serialize_documents(reversed(second))
    data = serialize_documents(first)
    assert data.endswith(b"\n") and b"\r" not in data and not data.startswith(b"\xef\xbb\xbf")
    path = tmp_path / "documents.jsonl"
    path.write_bytes(data)
    assert verify_jsonl_artifact(path, first) == sha256(data)
    assert verify_document_parity(sources, first)["status"] == "GREEN"


def test_empty_batch_is_deterministic() -> None:
    assert serialize_documents(build_product_documents([])) == b""


def test_duplicate_identity_rejected() -> None:
    with pytest.raises(DocumentContractError, match="duplicate"):
        build_product_documents([projection(), projection()])
    document = build_product_document(projection())
    with pytest.raises(DocumentContractError, match="duplicate"):
        serialize_documents([document, document])


def test_corrupted_document_and_artifact_rejected(tmp_path) -> None:
    document = build_product_document(projection())
    with pytest.raises(DocumentContractError, match="checksum"):
        serialize_documents([replace(document, text="corruption")])
    path = tmp_path / "corrupted.jsonl"
    path.write_bytes(serialize_documents([document]).replace(b"Lawn", b"Fake"))
    with pytest.raises(DocumentContractError):
        verify_jsonl_artifact(path, [document])


def test_parity_fails_for_drift_or_duplicate_documents() -> None:
    source = projection()
    changed = build_product_document(projection(name="Changed"))
    assert verify_document_parity([source], [changed])["status"] == "RED"
    assert verify_document_parity([source], [changed, changed])["status"] == "RED"


def test_no_dynamic_metadata_or_retriever_coupling() -> None:
    document = build_product_document(projection())
    record = document.record()
    assert set(record) == {"schema_version", "product_id", "fields", "text", "document_checksum"}
    assert set(record["fields"]) == {"name", "description", "colors"}
    for forbidden in [
        "price",
        "currency",
        "availability",
        "stock",
        "size",
        "brand",
        "category",
        "vendor",
        "image_url",
        "image_path",
        "sku",
        "listing_id",
        "external_product_id",
        "tokens",
        "scores",
        "rank",
        "embedding",
    ]:
        assert forbidden not in record and forbidden not in record["fields"]
        assert f"{forbidden}:" not in document.text.lower()
    assert "Khaadi" not in json.dumps(record)


def test_loader_sql_has_no_commercial_or_fixture_dependencies() -> None:
    for forbidden in [
        "catalog.listings",
        "inventory_balances",
        "external_refs",
        "product_images",
        "Khaadi",
    ]:
        assert forbidden not in PROJECTION_SQL


def test_shared_normalization_matches_previous_gates() -> None:
    from sahulat_text.ingestion.contracts import normalize_ingestion_text
    from sahulat_text.metadata_audit import normalize_text as audit_normalize

    assert normalize_text is normalize_ingestion_text is audit_normalize
    assert normalize_text(" Ｂlue\x00  Shirt\n ") == "Blue Shirt"


def test_different_unicode_tables_fail_explicitly(monkeypatch) -> None:
    monkeypatch.setattr("sahulat_text.normalization.unicodedata.unidata_version", "99.0.0")
    with pytest.raises(ValueError, match="Unicode"):
        build_product_document(projection())


def test_database_config_repr_never_exposes_password(tmp_path) -> None:
    config = DatabaseConfig(
        "localhost", 5432, "synthetic", "synthetic", "secret-sentinel", tmp_path
    )
    assert "secret-sentinel" not in repr(config)


def test_markdown_reproduces_from_canonical_json_evidence() -> None:
    synthetic_evidence = {
        "status": "GREEN",
        "manifest": {
            "db_contract_version": "synthetic-test-contract",
            "artifact_checksum": sha256(b""),
            "output_bytes": 0,
            "fixture_lineage": None,
            "counts": {"documents_generated": 0, "canonical_products_read": 0},
        },
        "observations": {"load_seconds": 0.1, "build_seconds": 0.2, "artifact_write_seconds": 0.3},
        "parity": {"status": "GREEN"},
        "determinism": True,
    }
    reloaded = json.loads(canonical_json_bytes(synthetic_evidence))
    assert render_build_report(synthetic_evidence) == render_build_report(reloaded)
