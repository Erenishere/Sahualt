"""Register/verify immutable corpus snapshots without reading or modifying PostgreSQL."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

from .artifacts import atomic_write
from .builder import SCHEMA_VERSION, build_product_documents, serialize_documents
from .projection import CanonicalProductProjection, DocumentContractError
from .serialization import canonical_json_bytes, sha256

DEFAULT_REGISTRY = Path("configs/corpora/product_text_v1.json")


def _portable_path(root: Path, reference: str) -> Path:
    if not isinstance(reference, str) or not reference or "\\" in reference or ":" in reference:
        raise DocumentContractError("corpus paths must use portable relative references")
    path = root / reference
    if Path(reference).is_absolute() or not path.resolve().is_relative_to(root.resolve()):
        raise DocumentContractError("corpus path escapes the repository")
    return path


def _verify_payload(registry: dict[str, Any], payload: bytes, manifest_bytes: bytes) -> None:
    if registry["status"] != "FROZEN" or registry["schema_version"] != SCHEMA_VERSION:
        raise DocumentContractError("registry is not a frozen product-text-v1 corpus")
    if sha256(payload) != f"sha256:{registry['artifact_sha256']}":
        raise DocumentContractError("frozen corpus checksum drift")
    if sha256(manifest_bytes) != f"sha256:{registry['manifest_sha256']}":
        raise DocumentContractError("frozen manifest checksum drift")
    manifest = json.loads(manifest_bytes)
    manifest_payload = {key: value for key, value in manifest.items() if key != "manifest_checksum"}
    if sha256(canonical_json_bytes(manifest_payload)) != manifest["manifest_checksum"]:
        raise DocumentContractError("invalid source manifest checksum")
    metadata = {
        "normalization_version": manifest.get("normalization_version"),
        "builder_version": manifest.get("builder_version"),
        "db_contract_version": manifest.get("db_contract_version"),
        "adr": manifest.get("adr_version"),
    }
    if any(key in registry and registry[key] != value for key, value in metadata.items()):
        raise DocumentContractError("registry provenance disagrees with the frozen manifest")
    if "runtime" in registry and registry["runtime"] != {
        "python": "3.12",
        "unicode": manifest.get("unicode_version"),
    }:
        raise DocumentContractError("registry runtime disagrees with the frozen normalization")
    if "fixture_semantic_checksum" in registry and registry["fixture_semantic_checksum"] != (
        manifest.get("fixture_lineage") or {}
    ).get("fixture_semantic_checksum"):
        raise DocumentContractError("registry fixture lineage disagrees with the frozen manifest")
    if (
        manifest["document_schema_version"] != SCHEMA_VERSION
        or manifest["artifact_checksum"] != sha256(payload)
        or manifest["output_bytes"] != len(payload)
    ):
        raise DocumentContractError("manifest and corpus disagree")
    records = [json.loads(line) for line in payload.splitlines()]
    projections = [
        CanonicalProductProjection(
            UUID(record["product_id"]),
            record["fields"]["name"],
            record["fields"]["description"],
            tuple(record["fields"]["colors"]),
        )
        for record in records
    ]
    documents = build_product_documents(projections)
    if serialize_documents(documents) != payload:
        raise DocumentContractError("corpus differs from canonical product-text-v1 serialization")
    if (
        len(documents) != registry["record_count"]
        or len(documents) != manifest["counts"]["documents_generated"]
    ):
        raise DocumentContractError("frozen corpus record count mismatch")
    if manifest["document_checksums"] != {
        str(document.product_id): document.document_checksum for document in documents
    }:
        raise DocumentContractError("manifest document checksums disagree")


def verify_registered_corpus(
    registry_path: Path = DEFAULT_REGISTRY, *, repository_root: Path = Path(".")
) -> dict[str, Any]:
    registry: dict[str, Any] = json.loads(registry_path.read_bytes())
    payload = _portable_path(repository_root, registry["artifact_path"]).read_bytes()
    manifest = _portable_path(repository_root, registry["manifest_path"]).read_bytes()
    _verify_payload(registry, payload, manifest)
    return registry


def freeze_registered_corpus(
    registry_path: Path = DEFAULT_REGISTRY, *, repository_root: Path = Path(".")
) -> dict[str, Any]:
    registry: dict[str, Any] = json.loads(registry_path.read_bytes())
    payload = _portable_path(repository_root, registry["build_input"]["artifact_path"]).read_bytes()
    manifest = _portable_path(
        repository_root, registry["build_input"]["manifest_path"]
    ).read_bytes()
    _verify_payload(registry, payload, manifest)
    destinations = [
        (_portable_path(repository_root, registry["artifact_path"]), payload),
        (_portable_path(repository_root, registry["manifest_path"]), manifest),
    ]
    # Preflight both files before writing either; never silently repair a frozen snapshot.
    for path, content in destinations:
        if path.exists() and path.read_bytes() != content:
            raise DocumentContractError("existing frozen snapshot drift; refusing overwrite")
    for path, content in destinations:
        if not path.exists():
            atomic_write(path, content)
    return verify_registered_corpus(registry_path, repository_root=repository_root)
