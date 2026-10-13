from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..canonical import content_checksum

GATE1_AUDIT_PATH = Path("artifacts/product_metadata_audit/product_metadata_audit.json")
VISUAL_AUDIT_PATH = Path("reports/dataset_audit.json")
VISUAL_SPLIT_PATH = Path("artifacts/eval_visual_v1/split.json")
EXPECTED_GATE1_VERSION = "khaadi-contract-mapping-v2"
EXPECTED_SOURCE_SYSTEM = "khaadi-v1"
EXPECTED_GATE1_EVIDENCE = "sha256:687798fbffad8ec6c2998145ed698b57b8e6a22433df50a95bfa66c84996563e"
EXPECTED_SOURCE_SHA256 = "bbb0a5b3eed1bfbe6dd7c2add33cff7d0420db82e1d9f961ecdd61e1d391119e"
EXPECTED_MANIFEST_SHA256 = "3b9ea0b9365ea196b8a67b91aca0e28f7ad8ac42aba1fef903fa428e636be994"
EXPECTED_SOURCE_METADATA_SHA256 = "c03bcd001e905ee6c4d9a595dbaf9d403b8820c6d86aa52b0b57311fd756d58f"
EXPECTED_DATASET_VERSION = "1"
EXPECTED_VALID_PRODUCTS = 400
EXPECTED_COLUMNS = (
    "ID",
    "Product Name",
    "Product Description",
    "Price",
    "Availability",
    "Color",
    "Img Path",
    "Product Link",
)


class KhaadiAuthorityError(ValueError):
    """Raised when current source bytes differ from the audited authority."""


@dataclass(frozen=True, slots=True)
class KhaadiAuthority:
    audit: dict[str, Any]
    source_metadata: dict[str, Any]
    rows: tuple[dict[str, str], ...]
    visual_retained: tuple[dict[str, Any], ...]
    visual_excluded: tuple[dict[str, Any], ...]
    source_path: Path
    source_path_record: str
    source_sha256: str
    manifest_path: Path
    manifest_path_record: str
    manifest_sha256: str
    visual_audit_sha256: str
    dataset_version: str
    valid_product_ids: frozenset[str]
    quarantined_products: tuple[dict[str, Any], ...]


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise KhaadiAuthorityError(f"Unable to read authoritative JSON artifact: {path}") from error


def _file_sha256(path: Path) -> str:
    try:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
    except OSError as error:
        raise KhaadiAuthorityError(f"Unable to read authoritative source: {path}") from error


def _resolve_repository_path(recorded_path: str, repository_root: Path) -> Path:
    path = (repository_root / recorded_path).resolve()
    if Path(recorded_path).is_absolute() or not path.is_relative_to(repository_root.resolve()):
        raise KhaadiAuthorityError("Audit artifact contains an unsafe source path")
    return path


def _verify_gate1_evidence(audit: dict[str, Any]) -> None:
    if audit.get("audit_version") != EXPECTED_GATE1_VERSION:
        raise KhaadiAuthorityError("Gate 1 audit version does not match Fixture Ingestion V1")
    evidence = audit.get("evidence_sha256")
    payload = {key: value for key, value in audit.items() if key != "evidence_sha256"}
    if evidence != f"sha256:{content_checksum(payload)}":
        raise KhaadiAuthorityError("Gate 1 audit evidence checksum is invalid")
    if evidence != EXPECTED_GATE1_EVIDENCE:
        raise KhaadiAuthorityError("Gate 1 audit evidence differs from the frozen fixture")
    if audit.get("contract_fitness", {}).get("overall_readiness_verdict") != "GREEN":
        raise KhaadiAuthorityError("Gate 1 audit is not GREEN")


def _read_csv(path: Path) -> tuple[dict[str, str], ...]:
    try:
        with path.open("r", encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream, strict=True)
            if tuple(reader.fieldnames or ()) != EXPECTED_COLUMNS:
                raise KhaadiAuthorityError("Khaadi CSV columns differ from the audited fixture")
            rows = tuple(dict(row) for row in reader)
    except (OSError, UnicodeDecodeError, csv.Error) as error:
        raise KhaadiAuthorityError("Khaadi CSV cannot be parsed deterministically") from error
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise KhaadiAuthorityError("Khaadi CSV contains malformed column cardinality")
    return rows


def _verify_visual_authority(
    repository_root: Path,
    manifest: list[dict[str, Any]],
    visual_audit: dict[str, Any],
    visual_split: dict[str, Any],
    valid_product_ids: frozenset[str],
    *,
    verify_image_binaries: bool,
) -> None:
    if visual_audit.get("manifest_sha256") != content_checksum(manifest):
        raise KhaadiAuthorityError("Visual audit does not match the authoritative image manifest")
    if visual_audit.get("retained_sha256") != content_checksum(visual_audit.get("retained")):
        raise KhaadiAuthorityError("Visual retained-image evidence checksum is invalid")
    if visual_split.get("audit_sha256") != content_checksum(visual_audit):
        raise KhaadiAuthorityError("Visual audit differs from the frozen EVAL-VISUAL-V1 split")
    if visual_split.get("retained_sha256") != visual_audit.get("retained_sha256"):
        raise KhaadiAuthorityError("Visual retained-image set differs from EVAL-VISUAL-V1")

    manifest_by_id: dict[str, dict[str, Any]] = {}
    for row in manifest:
        image_id = row.get("image_id")
        if not isinstance(image_id, str) or image_id in manifest_by_id:
            raise KhaadiAuthorityError("Image manifest contains an invalid or duplicate image ID")
        manifest_by_id[image_id] = row

    image_root = (repository_root / "data/raw/khaadi").resolve()
    for retained in visual_audit.get("retained", []):
        image_id = retained.get("image_id")
        manifest_row = manifest_by_id.get(image_id)
        if manifest_row is None or any(
            manifest_row.get(field) != retained.get(field)
            for field in ("image_id", "product_id", "image_path")
        ):
            raise KhaadiAuthorityError("Visual retained image has no exact manifest lineage")
        if retained.get("product_id") not in valid_product_ids:
            raise KhaadiAuthorityError("Visual retained image references a non-importable product")
        relative_path = retained.get("image_path")
        if not isinstance(relative_path, str):
            raise KhaadiAuthorityError("Visual retained image path is invalid")
        image_path = (image_root / relative_path).resolve()
        if Path(relative_path).is_absolute() or not image_path.is_relative_to(image_root):
            raise KhaadiAuthorityError("Visual retained image path escapes the fixture root")
        if verify_image_binaries and _file_sha256(image_path) != retained.get("binary_sha256"):
            raise KhaadiAuthorityError(f"Image binary checksum drift: {image_id}")


def load_khaadi_authority(
    repository_root: Path = Path("."), *, verify_image_binaries: bool = True
) -> KhaadiAuthority:
    root = repository_root.resolve()
    audit = _read_json(root / GATE1_AUDIT_PATH)
    if not isinstance(audit, dict):
        raise KhaadiAuthorityError("Gate 1 audit must be a JSON object")
    _verify_gate1_evidence(audit)

    source_record = audit["source"]
    source_path_record = source_record["path"]
    source_path = _resolve_repository_path(source_path_record, root)
    source_sha256 = _file_sha256(source_path)
    if source_sha256 != source_record["sha256"] or source_sha256 != EXPECTED_SOURCE_SHA256:
        raise KhaadiAuthorityError(
            "Khaadi source checksum differs from Gate 1; rerun Gate 1 audit before importing"
        )
    rows = _read_csv(source_path)
    if len(rows) != source_record["parsed_rows"]:
        raise KhaadiAuthorityError("Parsed Khaadi row count differs from Gate 1")

    related = audit["related_artifacts"]
    manifest_record = related["manifest"]
    manifest_path_record = manifest_record["path"]
    manifest_path = _resolve_repository_path(manifest_path_record, root)
    manifest_sha256 = _file_sha256(manifest_path)
    if manifest_sha256 != manifest_record["sha256"] or manifest_sha256 != EXPECTED_MANIFEST_SHA256:
        raise KhaadiAuthorityError("Image manifest checksum differs from Gate 1")
    manifest = _read_json(manifest_path)
    if not isinstance(manifest, list) or len(manifest) != manifest_record["record_count"]:
        raise KhaadiAuthorityError("Image manifest cardinality differs from Gate 1")

    source_metadata_record = related["source_metadata"]
    source_metadata_path = _resolve_repository_path(source_metadata_record["path"], root)
    source_metadata_sha256 = _file_sha256(source_metadata_path)
    if (
        source_metadata_sha256 != source_metadata_record["sha256"]
        or source_metadata_sha256 != EXPECTED_SOURCE_METADATA_SHA256
    ):
        raise KhaadiAuthorityError("Dataset source metadata checksum differs from Gate 1")
    source_metadata = _read_json(source_metadata_path)
    if not isinstance(source_metadata, dict):
        raise KhaadiAuthorityError("Dataset source metadata must be a JSON object")
    dataset_version = str(source_metadata.get("dataset_version", ""))
    if (
        dataset_version != str(source_metadata_record["declared_dataset_version"])
        or dataset_version != EXPECTED_DATASET_VERSION
    ):
        raise KhaadiAuthorityError("Dataset version differs from Gate 1")

    exclusions = audit["exclusions_and_quarantine"]
    valid_product_ids = frozenset(exclusions["valid_canonical_document_product_ids"])
    if (
        len(valid_product_ids) != exclusions["valid_canonical_document_candidate_count"]
        or len(valid_product_ids) != EXPECTED_VALID_PRODUCTS
    ):
        raise KhaadiAuthorityError("Gate 1 valid-product evidence is internally inconsistent")
    csv_ids = {row["ID"] for row in rows if row["ID"]}
    quarantined = tuple(exclusions["quarantined_products"])
    quarantined_ids = {
        item["product_id"] for item in quarantined if isinstance(item.get("product_id"), str)
    }
    if csv_ids != valid_product_ids | quarantined_ids:
        raise KhaadiAuthorityError("CSV product IDs differ from Gate 1 dispositions")

    visual_audit = _read_json(root / VISUAL_AUDIT_PATH)
    visual_split = _read_json(root / VISUAL_SPLIT_PATH)
    if not isinstance(visual_audit, dict) or not isinstance(visual_split, dict):
        raise KhaadiAuthorityError("Visual evidence artifacts must be JSON objects")
    _verify_visual_authority(
        root,
        manifest,
        visual_audit,
        visual_split,
        valid_product_ids,
        verify_image_binaries=verify_image_binaries,
    )

    return KhaadiAuthority(
        audit=audit,
        source_metadata=source_metadata,
        rows=rows,
        visual_retained=tuple(visual_audit["retained"]),
        visual_excluded=tuple(visual_audit["excluded"]),
        source_path=source_path,
        source_path_record=source_path_record,
        source_sha256=source_sha256,
        manifest_path=manifest_path,
        manifest_path_record=manifest_path_record,
        manifest_sha256=manifest_sha256,
        visual_audit_sha256=content_checksum(visual_audit),
        dataset_version=dataset_version,
        valid_product_ids=valid_product_ids,
        quarantined_products=quarantined,
    )
