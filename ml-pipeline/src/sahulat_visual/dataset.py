import hashlib
import logging
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .domain import ImageRecord
from .errors import DatasetError, InvalidImageError
from .images import DEFAULT_POLICY, ImagePolicy, load_image, pixel_hash, read_bytes
from .io import content_hash, read_json, write_json

logger = logging.getLogger(__name__)


def resolve_image(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(root.resolve()):
        raise DatasetError("Manifest image paths must stay inside the dataset root")
    return path


def read_manifest(path: Path) -> list[dict[str, Any]]:
    rows = read_json(path)
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise DatasetError("Manifest must be a JSON array of image metadata objects")
    return rows


def audit_dataset(
    rows: list[dict[str, Any]], root: Path, policy: ImagePolicy = DEFAULT_POLICY
) -> dict[str, Any]:
    """Exclude every cross-label duplicate; retain one same-label representative."""
    excluded: list[dict[str, Any]] = []
    valid: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for position, row in enumerate(rows):
        image_id = row.get("image_id")
        if isinstance(image_id, str) and image_id in seen_ids:
            # Ambiguous IDs cannot safely address a frozen split, even if one is corrupt.
            raise DatasetError(f"Duplicate image_id in manifest: {image_id}")
        if isinstance(image_id, str):
            seen_ids.add(image_id)
        try:
            record = ImageRecord(
                row.get("image_id", ""), row.get("product_id", ""), row.get("image_path", "")
            )
        except (TypeError, ValueError):
            excluded.append(
                {"row": position, "image_id": image_id, "reason": "missing-or-invalid-metadata"}
            )
            continue
        try:
            path = resolve_image(root, record.image_path)
            if not path.is_file():
                reason = "missing-file"
                raise InvalidImageError(reason)
            reason = "invalid-or-unreadable-image"
            data = read_bytes(path, policy)
            image = load_image(data, policy)
            valid.append(
                {
                    **asdict(record),
                    "binary_sha256": hashlib.sha256(data).hexdigest(),
                    "pixel_sha256": pixel_hash(image),
                    "width": image.width,
                    "height": image.height,
                }
            )
            image.close()
        except (InvalidImageError, DatasetError) as exc:
            excluded.append(
                {
                    "row": position,
                    **asdict(record),
                    "reason": reason if isinstance(exc, InvalidImageError) else "unsafe-path",
                    "detail": str(exc),
                }
            )
            logger.warning(
                "catalogue_image_skipped", extra={"image_id": record.image_id, "reason": str(exc)}
            )
    binary_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    pixel_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in valid:
        binary_groups[row["binary_sha256"]].append(row)
        pixel_groups[row["pixel_sha256"]].append(row)
    conflicts: set[str] = set()
    for group in (*binary_groups.values(), *pixel_groups.values()):
        if len({r["product_id"] for r in group}) > 1:
            conflicts.update(r["image_id"] for r in group)
    retained = []
    for group in pixel_groups.values():
        ordered = sorted(group, key=lambda r: r["image_id"])
        for i, row in enumerate(ordered):
            duplicate_reason = (
                "conflicting-product-label"
                if row["image_id"] in conflicts
                else ("within-product-exact-duplicate" if i > 0 else None)
            )
            if duplicate_reason:
                excluded.append({**row, "reason": duplicate_reason})
            else:
                retained.append(row)
    retained.sort(key=lambda r: r["image_id"])
    groups = lambda mapping: [  # noqa: E731
        {
            "hash": key,
            "image_ids": sorted(r["image_id"] for r in group),
            "product_ids": sorted({r["product_id"] for r in group}),
        }
        for key, group in sorted(mapping.items())
        if len(group) > 1
    ]
    return {
        "audit_version": "binary-and-exif-rgb-sha256-v1",
        "policy": asdict(policy),
        "manifest_sha256": content_hash(rows),
        "retained_sha256": content_hash(retained),
        "raw_image_records": len(rows),
        "raw_products": len(
            {
                r.get("product_id")
                for r in rows
                if isinstance(r.get("product_id"), str) and r["product_id"].strip()
            }
        ),
        "retained_images": len(retained),
        "retained_products": len({r["product_id"] for r in retained}),
        "excluded_count": len(excluded),
        "excluded": excluded,
        "retained": retained,
        "exclusions_by_reason": dict(Counter(row["reason"] for row in excluded)),
        "invalid_image_counts_by_detail": dict(
            Counter(
                row["detail"] for row in excluded if row["reason"] == "invalid-or-unreadable-image"
            )
        ),
        "binary_duplicate_groups": groups(binary_groups),
        "pixel_duplicate_groups": groups(pixel_groups),
    }


def make_split(audit: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    settings = config["split"]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in audit["retained"]:
        grouped[row["product_id"]].append(row)
    query: list[str] = []
    gallery: list[str] = []
    singletons: list[str] = []
    for product_id, rows in sorted(grouped.items()):
        ordered = sorted(
            rows,
            key=lambda r: (
                hashlib.sha256(f"{settings['seed']}:{r['image_id']}".encode()).hexdigest(),
                r["image_id"],
            ),
        )
        count = min(len(rows) - 1, max(1, int(len(rows) * settings["query_fraction"])))
        if len(rows) == 1:
            singletons.append(product_id)
        query.extend(r["image_id"] for r in ordered[:count])
        gallery.extend(r["image_id"] for r in ordered[count:])
    if not query:
        raise DatasetError("No evaluable products with two distinct images")
    payload = {
        "evaluation_version": config["evaluation_version"],
        "protocol_sha256": protocol_hash(config),
        "audit_sha256": content_hash(audit),
        "retained_sha256": audit["retained_sha256"],
        "provenance": settings["provenance"],
        "seed": settings["seed"],
        "query_ids": sorted(query),
        "gallery_ids": sorted(gallery),
        "statistics": {
            "queries": len(query),
            "gallery": len(gallery),
            "products_evaluated": len(grouped) - len(singletons),
            "singleton_gallery_only_products": singletons,
        },
    }
    return {**payload, "split_sha256": content_hash(payload)}


def protocol_hash(config: dict[str, Any]) -> str:
    # File locations are deployment details, not the evaluation protocol.
    import copy

    protocol = copy.deepcopy(config)
    protocol["dataset"].pop("root", None)
    protocol["dataset"].pop("manifest", None)
    protocol["split"].pop("artifact", None)
    return content_hash(protocol)


def verify_split(split: dict[str, Any], audit: dict[str, Any], config: dict[str, Any]) -> None:
    expected = make_split(audit, config)
    if expected != split:
        raise DatasetError(
            "Frozen split, dataset or protocol changed; create a new evaluation version"
        )


def freeze_split(path: Path, audit: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    split = make_split(audit, config)
    if path.exists():
        verify_split(read_json(path), audit, config)
    else:
        write_json(path, split)
    return split


def records_from_audit(audit: dict[str, Any], ids: list[str] | None = None) -> list[ImageRecord]:
    by_id = {
        r["image_id"]: ImageRecord(**{k: r[k] for k in ImageRecord.__dataclass_fields__})
        for r in audit["retained"]
    }
    return [by_id[key] for key in (ids if ids is not None else sorted(by_id))]
