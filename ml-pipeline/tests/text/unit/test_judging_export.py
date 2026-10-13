from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path
from uuid import UUID

import pytest

from sahulat_text.documents import CanonicalProductProjection
from sahulat_text.documents.builder import build_product_documents, serialize_documents
from sahulat_text.documents.corpus import freeze_registered_corpus
from sahulat_text.documents.serialization import canonical_json_bytes, sha256
from sahulat_text.evaluation.judging_export import (
    export_judging_products_csv,
    load_judging_products,
    render_judging_products_csv,
)
from sahulat_text.evaluation.protocol import TextEvaluationError


def _synthetic_registry(root: Path, *, record_count: int = 2) -> tuple[Path, dict[str, object]]:
    documents = build_product_documents(
        [
            CanonicalProductProjection(
                UUID(int=index),
                f"Name {index}",
                f"Description {index}.",
                ("Blue",) if index == 1 else tuple(),
            )
            for index in range(1, record_count + 1)
        ]
    )
    payload = serialize_documents(documents)
    manifest = {
        "document_schema_version": "product-text-v1",
        "artifact_checksum": sha256(payload),
        "output_bytes": len(payload),
        "counts": {"documents_generated": len(documents)},
        "document_checksums": {
            str(document.product_id): document.document_checksum for document in documents
        },
        "normalization_version": "product-normalization-v1",
        "builder_version": "product-text-builder-v1",
        "db_contract_version": "DB-CONTRACT-V1",
        "adr_version": "ADR-ML-004-v1",
        "unicode_version": "15.0.0",
        "fixture_lineage": {"fixture_semantic_checksum": "0" * 64},
    }
    manifest["manifest_checksum"] = sha256(canonical_json_bytes(manifest))
    manifest_bytes = canonical_json_bytes(manifest) + b"\n"
    (root / "working.jsonl").write_bytes(payload)
    (root / "working.manifest.json").write_bytes(manifest_bytes)
    registry: dict[str, object] = {
        "corpus_id": "SYNTHETIC-JUDGING-EXPORT",
        "status": "FROZEN",
        "schema_version": "product-text-v1",
        "record_count": len(documents),
        "artifact_sha256": sha256(payload).removeprefix("sha256:"),
        "manifest_sha256": sha256(manifest_bytes).removeprefix("sha256:"),
        "artifact_path": "snapshot/documents.jsonl",
        "manifest_path": "snapshot/manifest.json",
        "build_input": {"artifact_path": "working.jsonl", "manifest_path": "working.manifest.json"},
        "normalization_version": "product-normalization-v1",
        "builder_version": "product-text-builder-v1",
        "adr": "ADR-ML-004-v1",
        "db_contract_version": "DB-CONTRACT-V1",
        "runtime": {"python": "3.12", "unicode": "15.0.0"},
        "fixture_semantic_checksum": "0" * 64,
    }
    path = root / "registry.json"
    path.write_bytes(canonical_json_bytes(registry))
    freeze_registered_corpus(path, repository_root=root)
    return path, registry


def test_render_csv_columns_and_sorting(tmp_path: Path) -> None:
    registry_path, _ = _synthetic_registry(tmp_path)
    rows = load_judging_products(
        repository_root=tmp_path,
        registry_path=registry_path,
        protocol=None,
    )
    payload = render_judging_products_csv(rows).decode("utf-8")
    reader = csv.DictReader(StringIO(payload))
    assert reader.fieldnames == ["row_number", "product_id", "name", "description", "color"]
    records = list(reader)
    assert len(records) == 2
    assert records[0]["product_id"] < records[1]["product_id"]
    assert records[0]["row_number"] == "1"
    assert records[1]["color"] == ""


def test_export_refuses_existing_output_without_overwrite(tmp_path: Path) -> None:
    registry_path, _ = _synthetic_registry(tmp_path)
    output = tmp_path / "judging.csv"
    export_judging_products_csv(
        output,
        repository_root=tmp_path,
        registry_path=registry_path,
        bind_eval_protocol=False,
        overwrite=False,
    )
    with pytest.raises(TextEvaluationError, match="output already exists"):
        export_judging_products_csv(
            output,
            repository_root=tmp_path,
            registry_path=registry_path,
            bind_eval_protocol=False,
            overwrite=False,
        )


def test_export_overwrite_replaces_bytes(tmp_path: Path) -> None:
    registry_path, _ = _synthetic_registry(tmp_path)
    output = tmp_path / "judging.csv"
    export_judging_products_csv(
        output,
        repository_root=tmp_path,
        registry_path=registry_path,
        bind_eval_protocol=False,
    )
    first = output.read_bytes()
    export_judging_products_csv(
        output,
        repository_root=tmp_path,
        registry_path=registry_path,
        bind_eval_protocol=False,
        overwrite=True,
    )
    assert output.read_bytes() == first


@pytest.mark.skipif(
    not Path("configs/corpora/product_text_v1.json").exists(),
    reason="frozen production corpus registry not present",
)
def test_export_frozen_eval_corpus_has_400_products(tmp_path: Path) -> None:
    output = tmp_path / "judging_products.csv"
    summary = export_judging_products_csv(output, repository_root=Path("."), overwrite=True)
    assert summary["product_count"] == 400
    assert summary["unique_product_ids"] == 400
    reader = csv.DictReader(output.read_text(encoding="utf-8").splitlines())
    rows = list(reader)
    assert len(rows) == 400
    assert len({row["product_id"] for row in rows}) == 400
