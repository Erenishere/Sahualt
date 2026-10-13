from __future__ import annotations

import json
from uuid import UUID

import pytest

from sahulat_text.documents import CanonicalProductProjection, DocumentContractError
from sahulat_text.documents.builder import build_product_documents, serialize_documents
from sahulat_text.documents.corpus import freeze_registered_corpus, verify_registered_corpus
from sahulat_text.documents.serialization import canonical_json_bytes, sha256


@pytest.fixture
def registered_fixture(tmp_path):
    # Synthetic records test registration mechanics; they are not evaluation evidence.
    documents = build_product_documents(
        [CanonicalProductProjection(UUID(int=1), "Synthetic", "Test description.", ("Blue",))]
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
    }
    manifest["manifest_checksum"] = sha256(canonical_json_bytes(manifest))
    manifest_bytes = canonical_json_bytes(manifest) + b"\n"
    (tmp_path / "working.jsonl").write_bytes(payload)
    (tmp_path / "working.manifest.json").write_bytes(manifest_bytes)
    registry = {
        "corpus_id": "SYNTHETIC-TEST-CORPUS",
        "status": "FROZEN",
        "schema_version": "product-text-v1",
        "record_count": len(documents),
        "artifact_sha256": sha256(payload).removeprefix("sha256:"),
        "manifest_sha256": sha256(manifest_bytes).removeprefix("sha256:"),
        "artifact_path": "snapshot/documents.jsonl",
        "manifest_path": "snapshot/manifest.json",
        "build_input": {"artifact_path": "working.jsonl", "manifest_path": "working.manifest.json"},
    }
    path = tmp_path / "registry.json"
    path.write_bytes(canonical_json_bytes(registry))
    return tmp_path, path, registry, payload


def test_registration_is_deterministic_idempotent_and_verified(registered_fixture) -> None:
    root, path, registry, payload = registered_fixture
    assert freeze_registered_corpus(path, repository_root=root) == registry
    before = (root / registry["artifact_path"]).stat().st_mtime_ns
    assert freeze_registered_corpus(path, repository_root=root) == registry
    assert (root / registry["artifact_path"]).stat().st_mtime_ns == before
    assert (root / registry["artifact_path"]).read_bytes() == payload
    assert verify_registered_corpus(path, repository_root=root) == registry


def test_working_build_changes_do_not_change_frozen_snapshot(registered_fixture) -> None:
    root, path, registry, _ = registered_fixture
    freeze_registered_corpus(path, repository_root=root)
    (root / "working.jsonl").write_bytes(b"changed working build\n")
    assert verify_registered_corpus(path, repository_root=root) == registry
    with pytest.raises(DocumentContractError, match="checksum drift"):
        freeze_registered_corpus(path, repository_root=root)


@pytest.mark.parametrize("file", ["working.jsonl", "working.manifest.json"])
def test_source_drift_refused_before_snapshot_writes(registered_fixture, file) -> None:
    root, path, _, _ = registered_fixture
    (root / file).write_bytes(b"drift\n")
    with pytest.raises(DocumentContractError, match="checksum drift"):
        freeze_registered_corpus(path, repository_root=root)
    assert not (root / "snapshot").exists()


def test_corrupted_frozen_file_is_never_silently_repaired(registered_fixture) -> None:
    root, path, registry, _ = registered_fixture
    freeze_registered_corpus(path, repository_root=root)
    frozen = root / registry["artifact_path"]
    frozen.write_bytes(b"corrupted snapshot\n")
    with pytest.raises(DocumentContractError, match="refusing overwrite"):
        freeze_registered_corpus(path, repository_root=root)
    with pytest.raises(DocumentContractError, match="checksum drift"):
        verify_registered_corpus(path, repository_root=root)
    assert frozen.read_bytes() == b"corrupted snapshot\n"


@pytest.mark.parametrize(
    "reference",
    ["../outside.jsonl", "/outside.jsonl", "C:/private.jsonl", "\\\\server\\private.jsonl"],
)
def test_nonportable_or_escaping_paths_rejected(registered_fixture, reference) -> None:
    root, path, registry, _ = registered_fixture
    registry["build_input"]["artifact_path"] = reference
    path.write_bytes(canonical_json_bytes(registry))
    with pytest.raises(DocumentContractError, match="path"):
        freeze_registered_corpus(path, repository_root=root)


def test_incorrect_count_rejected(registered_fixture) -> None:
    root, path, registry, _ = registered_fixture
    registry["record_count"] = 99
    path.write_bytes(canonical_json_bytes(registry))
    with pytest.raises(DocumentContractError, match="count mismatch"):
        freeze_registered_corpus(path, repository_root=root)


@pytest.mark.parametrize(
    "metadata",
    [
        {"builder_version": "false-version"},
        {"runtime": {"python": "99.0", "unicode": "99.0.0"}},
        {"fixture_semantic_checksum": "false-lineage"},
    ],
)
def test_false_registry_provenance_rejected(registered_fixture, metadata) -> None:
    root, path, registry, _ = registered_fixture
    registry.update(metadata)
    path.write_bytes(canonical_json_bytes(registry))
    with pytest.raises(DocumentContractError, match="disagrees"):
        freeze_registered_corpus(path, repository_root=root)


def test_false_manifest_document_evidence_rejected(registered_fixture) -> None:
    root, path, registry, _ = registered_fixture
    manifest = json.loads((root / "working.manifest.json").read_bytes())
    manifest["document_checksums"] = {}
    manifest["manifest_checksum"] = sha256(
        canonical_json_bytes(
            {key: value for key, value in manifest.items() if key != "manifest_checksum"}
        )
    )
    data = canonical_json_bytes(manifest) + b"\n"
    (root / "working.manifest.json").write_bytes(data)
    registry["manifest_sha256"] = sha256(data).removeprefix("sha256:")
    path.write_bytes(canonical_json_bytes(registry))
    with pytest.raises(DocumentContractError, match="document checksums"):
        freeze_registered_corpus(path, repository_root=root)
