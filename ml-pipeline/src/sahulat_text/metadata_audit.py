from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import re
import tempfile
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import median
from typing import Any

from .normalization import normalization_steps, normalize_text

AUDIT_VERSION = "khaadi-contract-mapping-v2"
DOCUMENT_VERSION = "product-text-v1"
ADR_PATH = "docs/ADR-DATA-001-product-ingestion-and-search-metadata-contract.md"

REQUIRED_COLUMNS = (
    "ID",
    "Product Name",
    "Product Description",
    "Color",
    "Price",
    "Availability",
)
TEXT_COLUMNS = {
    "ID",
    "Product Name",
    "Product Description",
    "Color",
    "Availability",
    "Img Path",
    "Product Link",
}
PLACEHOLDER_VALUES = {
    "-",
    "--",
    "n/a",
    "na",
    "none",
    "not available",
    "null",
    "tbd",
    "unknown",
}
PRODUCTION_AVAILABILITY_VALUES = {"in_stock", "out_of_stock"}
PRICE_PATTERN = re.compile(r"^[+-]?(?:\d+(?:\.\d+)?|\.\d+)$")
COMPOUND_COLOR_PATTERN = re.compile(r"(?:[/,&+|]|\band\b)", re.IGNORECASE)

SOURCE_TO_CONTRACT = (
    {
        "source_field": "ID",
        "production_owner": "Product identity",
        "canonical_use": "Required opaque product_id",
    },
    {
        "source_field": "Product Name",
        "production_owner": "Product",
        "canonical_use": "Required product-text-v1 field",
    },
    {
        "source_field": "Product Description",
        "production_owner": "Product",
        "canonical_use": "Required product-text-v1 field",
    },
    {
        "source_field": "Color",
        "production_owner": "ProductVariant",
        "canonical_use": "Optional product-text-v1 variant-color input when present",
    },
    {
        "source_field": "Price",
        "production_owner": "Listing",
        "canonical_use": "Structured metadata only; excluded from canonical text",
    },
    {
        "source_field": "Availability",
        "production_owner": "Listing",
        "canonical_use": "Structured metadata only; excluded from canonical text",
    },
    {
        "source_field": "Img Path",
        "production_owner": "ProductImage",
        "canonical_use": "Evaluation image linkage only; excluded from canonical text",
    },
    {
        "source_field": "Product Link",
        "production_owner": "Fixture provenance",
        "canonical_use": "Evaluation provenance only; excluded from production contract",
    },
)

UNSUPPORTED_PRODUCTION_FIELDS = (
    "Currency",
    "Stock quantity",
    "Size",
    "Brand",
    "Category",
    "Tags",
    "Materials",
    "Gender",
    "Product type",
)


class MetadataAuditError(ValueError):
    """Raised when source metadata cannot be audited safely."""


@dataclass(frozen=True, slots=True)
class SourceRecord:
    position: int
    source_line_start: int
    source_line_end: int
    values: dict[str, str]


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _content_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return _sha256_bytes(payload)


def _decode_csv(raw: bytes) -> tuple[str, str]:
    encoding = "utf-8-sig" if raw.startswith(b"\xef\xbb\xbf") else "utf-8"
    try:
        return raw.decode(encoding), encoding
    except UnicodeDecodeError as exc:
        raise MetadataAuditError("CSV must be valid UTF-8 or UTF-8 with BOM") from exc


def _read_csv(path: Path) -> tuple[list[str], list[SourceRecord], dict[str, Any]]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise MetadataAuditError(f"Unable to read CSV: {path.name}") from exc
    text, encoding = _decode_csv(raw)
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|")
        reader = csv.reader(io.StringIO(text, newline=""), dialect=dialect, strict=True)
        headers = next(reader)
    except (csv.Error, StopIteration) as exc:
        raise MetadataAuditError("CSV header or dialect is malformed") from exc

    if not headers or any(not header.strip() for header in headers):
        raise MetadataAuditError("CSV contains an empty column name")
    if len(headers) != len(set(headers)):
        raise MetadataAuditError("CSV contains duplicate column names")
    missing_columns = sorted(set(REQUIRED_COLUMNS) - set(headers))
    if missing_columns:
        raise MetadataAuditError(f"CSV is missing required columns: {', '.join(missing_columns)}")

    records: list[SourceRecord] = []
    previous_line = reader.line_num
    try:
        for position, values in enumerate(reader, start=1):
            line_start = previous_line + 1
            line_end = reader.line_num
            previous_line = line_end
            if len(values) != len(headers):
                raise MetadataAuditError(
                    f"CSV record {position} has {len(values)} values for {len(headers)} columns"
                )
            records.append(
                SourceRecord(
                    position, line_start, line_end, dict(zip(headers, values, strict=True))
                )
            )
    except csv.Error as exc:
        raise MetadataAuditError(
            f"Malformed CSV record near physical line {reader.line_num}"
        ) from exc

    crlf_count = raw.count(b"\r\n")
    lf_count = raw.count(b"\n")
    cr_count = raw.count(b"\r")
    if crlf_count and crlf_count == lf_count == cr_count:
        line_ending = "CRLF"
    elif lf_count and not crlf_count and not cr_count:
        line_ending = "LF"
    elif cr_count and not lf_count:
        line_ending = "CR"
    else:
        line_ending = "mixed-or-none"
    physical_lines = len(raw.splitlines())
    source = {
        "bytes": len(raw),
        "sha256": _sha256_bytes(raw),
        "encoding": encoding,
        "has_byte_order_mark": raw.startswith(b"\xef\xbb\xbf"),
        "delimiter": dialect.delimiter,
        "quote_character": dialect.quotechar,
        "line_ending": line_ending,
        "physical_lines_including_header": physical_lines,
        "physical_rows": max(physical_lines - 1, 0),
        "parsed_rows": len(records),
        "columns": headers,
    }
    return headers, records, source


def _percentage(count: int, total: int) -> float:
    return round((count / total * 100) if total else 0.0, 6)


def _nearest_rank(values: list[int], percentile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def _field_statistics(
    field: str, records: list[SourceRecord], include_lengths: bool
) -> dict[str, Any]:
    raw_values = [record.values.get(field) for record in records]
    null_count = sum(value is None for value in raw_values)
    non_null_values = [value for value in raw_values if value is not None]
    blank_count = sum(value == "" for value in non_null_values)
    whitespace_only_count = sum(value != "" and not value.strip() for value in non_null_values)
    normalized_pairs = [
        (value, normalize_text(value)) for value in non_null_values if normalize_text(value)
    ]
    usable_raw = [raw for raw, _ in normalized_pairs]
    normalized_values = [normalized for _, normalized in normalized_pairs]
    raw_counts = Counter(usable_raw)
    normalized_to_raw: dict[str, set[str]] = defaultdict(set)
    for raw_value, normalized in normalized_pairs:
        normalized_to_raw[normalized].add(raw_value)
    collisions = [
        {"normalized_value": normalized, "raw_values": sorted(raw_group)}
        for normalized, raw_group in sorted(normalized_to_raw.items())
        if len(raw_group) > 1
    ]
    duplicate_groups = [(value, count) for value, count in raw_counts.items() if count > 1]
    samples: list[str] = []
    seen: set[str] = set()
    for value in usable_raw:
        if value not in seen:
            seen.add(value)
            samples.append(value)
        if len(samples) == 5:
            break
    placeholders = [
        {
            "value": value,
            "count": count,
            "source_rows": [
                record.source_line_start for record in records if record.values.get(field) == value
            ],
        }
        for value, count in sorted(raw_counts.items())
        if normalize_text(value).casefold() in PLACEHOLDER_VALUES
    ]
    impacts = Counter(
        impact
        for value in non_null_values
        for impact, changed in normalization_steps(value)[1].items()
        if changed
    )
    length_values = [len(value) for value in normalized_values]
    length_stats = None
    if include_lengths:
        length_stats = {
            "minimum": min(length_values) if length_values else None,
            "median": float(median(length_values)) if length_values else None,
            "p95_nearest_rank": _nearest_rank(length_values, 0.95),
            "maximum": max(length_values) if length_values else None,
        }
    return {
        "total_rows": len(records),
        "non_null_count": len(non_null_values),
        "null_count": null_count,
        "null_percentage": _percentage(null_count, len(records)),
        "blank_string_count": blank_count,
        "whitespace_only_count": whitespace_only_count,
        "usable_value_count": len(normalized_values),
        "usable_coverage_percentage": _percentage(len(normalized_values), len(records)),
        "distinct_value_count": len(raw_counts),
        "normalized_distinct_value_count": len(set(normalized_values)),
        "duplicate_values": {
            "group_count": len(duplicate_groups),
            "duplicate_row_count_beyond_first": sum(count - 1 for _, count in duplicate_groups),
            "largest_group_size": max((count for _, count in duplicate_groups), default=1),
            "top_groups": [
                {"value": value, "count": count}
                for value, count in sorted(duplicate_groups, key=lambda item: (-item[1], item[0]))[
                    :10
                ]
            ],
        },
        "representative_value_samples": samples,
        "suspicious_placeholder_values": placeholders,
        "text_length": length_stats,
        "control_character_value_count": sum(
            any(unicodedata.category(character) == "Cc" for character in value)
            for value in non_null_values
        ),
        "control_character_count": sum(
            unicodedata.category(character) == "Cc"
            for value in non_null_values
            for character in value
        ),
        "repeated_whitespace_value_count": sum(
            bool(re.search(r"\s{2,}", value)) for value in non_null_values
        ),
        "meaningful_unicode_value_count": sum(
            any(
                ord(character) > 127
                and not unicodedata.category(character).startswith("C")
                and not character.isspace()
                for character in value
            )
            for value in non_null_values
        ),
        "normalization_impact": {
            "unicode_normalization_value_count": impacts["unicode_normalization"],
            "control_character_removal_value_count": impacts["control_character_removal"],
            "outer_whitespace_trimming_value_count": impacts["outer_whitespace_trimming"],
            "repeated_whitespace_collapse_value_count": impacts["repeated_whitespace_collapse"],
            "any_change_value_count": sum(
                normalize_text(value) != value for value in non_null_values
            ),
            "collision_group_count": len(collisions),
            "collisions": collisions,
        },
    }


def _row_evidence(record: SourceRecord) -> dict[str, Any]:
    return {
        "record_position": record.position,
        "source_line_start": record.source_line_start,
        "source_line_end": record.source_line_end,
    }


def _product_id_integrity(
    headers: list[str], records: list[SourceRecord]
) -> tuple[dict[str, Any], set[str]]:
    by_id: dict[str, list[SourceRecord]] = defaultdict(list)
    missing_rows: list[dict[str, Any]] = []
    for record in records:
        product_id = normalize_text(record.values["ID"])
        if not product_id:
            missing_rows.append(_row_evidence(record))
        else:
            by_id[product_id].append(record)

    identical_groups: list[dict[str, Any]] = []
    conflicting_groups: list[dict[str, Any]] = []
    conflicting_ids: set[str] = set()
    for product_id, group in sorted(by_id.items()):
        if len(group) < 2:
            continue
        fingerprints = {
            tuple(
                (field, normalize_text(record.values[field])) for field in headers if field != "ID"
            )
            for record in group
        }
        if len(fingerprints) == 1:
            identical_groups.append(
                {
                    "product_id": product_id,
                    "record_count": len(group),
                    "records": [_row_evidence(record) for record in group],
                }
            )
            continue
        conflicting_ids.add(product_id)
        fields: list[dict[str, Any]] = []
        for field in headers:
            if field == "ID":
                continue
            values = {normalize_text(record.values[field]) for record in group}
            if len(values) > 1:
                fields.append(
                    {
                        "field": field,
                        "values": [
                            {
                                **_row_evidence(record),
                                "raw_value": record.values[field],
                                "normalized_value": normalize_text(record.values[field]),
                            }
                            for record in group
                        ],
                    }
                )
        conflicting_groups.append(
            {
                "product_id": product_id,
                "record_count": len(group),
                "records": [_row_evidence(record) for record in group],
                "conflicting_fields": fields,
                "disposition": "quarantine",
            }
        )

    duplicate_groups = [group for group in by_id.values() if len(group) > 1]
    return (
        {
            "missing_id_count": len(missing_rows),
            "blank_id_count": sum(record.values["ID"] == "" for record in records),
            "whitespace_only_id_count": sum(
                bool(record.values["ID"]) and not record.values["ID"].strip() for record in records
            ),
            "unique_product_id_count": len(by_id),
            "duplicate_id_group_count": len(duplicate_groups),
            "duplicate_id_record_count": sum(len(group) for group in duplicate_groups),
            "duplicate_id_rows_beyond_first": sum(len(group) - 1 for group in duplicate_groups),
            "identical_duplicate_group_count": len(identical_groups),
            "identical_duplicate_record_count_beyond_first": sum(
                group["record_count"] - 1 for group in identical_groups
            ),
            "conflicting_duplicate_group_count": len(conflicting_groups),
            "conflicting_duplicate_product_ids": sorted(conflicting_ids),
            "missing_id_rows": missing_rows,
            "identical_duplicate_groups": identical_groups,
            "conflicting_duplicate_groups": conflicting_groups,
        },
        conflicting_ids,
    )


def _decimal_string(value: Decimal) -> str:
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _price_analysis(records: list[SourceRecord]) -> dict[str, Any]:
    parsed: list[Decimal] = []
    failures: list[dict[str, Any]] = []
    missing_count = 0
    blank_count = 0
    whitespace_only_count = 0
    raw_samples: list[str] = []
    for record in records:
        raw = record.values.get("Price")
        if raw is None:
            missing_count += 1
            continue
        if raw == "":
            blank_count += 1
            continue
        if not raw.strip():
            whitespace_only_count += 1
            continue
        if raw not in raw_samples and len(raw_samples) < 10:
            raw_samples.append(raw)
        candidate = raw.strip()
        try:
            if not PRICE_PATTERN.fullmatch(candidate):
                raise InvalidOperation
            value = Decimal(candidate)
            if not value.is_finite():
                raise InvalidOperation
            parsed.append(value)
        except InvalidOperation:
            failures.append({**_row_evidence(record), "raw_value": raw})
    ordered = sorted(parsed)
    middle = None
    if ordered:
        middle = median(ordered)
    usable_count = len(records) - missing_count - blank_count - whitespace_only_count
    return {
        "source_data_type": "CSV string",
        "currency_inference_performed": False,
        "missing_count": missing_count,
        "blank_string_count": blank_count,
        "whitespace_only_count": whitespace_only_count,
        "parse_success_count": len(parsed),
        "parse_failure_count": len(failures),
        "parse_success_percentage_of_all_rows": _percentage(len(parsed), len(records)),
        "parse_success_percentage_of_usable_values": _percentage(len(parsed), usable_count),
        "negative_value_count": sum(value < 0 for value in parsed),
        "zero_value_count": sum(value == 0 for value in parsed),
        "minimum": _decimal_string(ordered[0]) if ordered else None,
        "median": _decimal_string(middle) if middle is not None else None,
        "maximum": _decimal_string(ordered[-1]) if ordered else None,
        "raw_representation_samples": raw_samples,
        "malformed_values": failures,
    }


def _availability_token(value: str) -> str:
    return re.sub(r"[^0-9a-z]+", "_", value.casefold()).strip("_")


def _availability_analysis(records: list[SourceRecord]) -> dict[str, Any]:
    raw_values = [record.values["Availability"] for record in records]
    usable = [value for value in raw_values if normalize_text(value)]
    raw_frequencies = Counter(usable)
    normalized_frequencies = Counter(normalize_text(value) for value in usable)
    candidate_mapping = {
        value: _availability_token(normalize_text(value)) for value in sorted(raw_frequencies)
    }
    unmapped = [
        value
        for value, candidate in candidate_mapping.items()
        if candidate not in PRODUCTION_AVAILABILITY_VALUES
    ]
    exact_values = set(normalized_frequencies).issubset(PRODUCTION_AVAILABILITY_VALUES)
    syntactic_mapping_possible = not unmapped
    if exact_values:
        assessment = "production_values_match_exactly"
    elif syntactic_mapping_possible:
        assessment = "appears_deterministic_but_requires_explicit_mapping_policy"
    else:
        assessment = "contains_values_without_an_apparent_production_mapping"
    return {
        "missing_count": sum(value is None for value in raw_values),
        "blank_string_count": sum(value == "" for value in raw_values),
        "whitespace_only_count": sum(bool(value) and not value.strip() for value in raw_values),
        "coverage_percentage": _percentage(len(usable), len(records)),
        "raw_frequencies": dict(sorted(raw_frequencies.items())),
        "normalized_frequencies": dict(sorted(normalized_frequencies.items())),
        "raw_distinct_values": sorted(raw_frequencies),
        "normalized_distinct_values": sorted(normalized_frequencies),
        "production_values_from_adr": sorted(PRODUCTION_AVAILABILITY_VALUES),
        "candidate_mapping_not_applied": candidate_mapping,
        "unmapped_values": unmapped,
        "suspicious_values": [
            value
            for value in sorted(raw_frequencies)
            if normalize_text(value).casefold() in PLACEHOLDER_VALUES or value in unmapped
        ],
        "mapping_applied": False,
        "mapping_assessment": assessment,
    }


def _metadata_relationship(
    path: Path | None, logical_path: str | None, expected_type: type
) -> tuple[Any | None, dict[str, Any] | None]:
    if path is None:
        return None, None
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MetadataAuditError(f"Malformed related JSON artifact: {path.name}") from exc
    if not isinstance(value, expected_type):
        raise MetadataAuditError(f"Related JSON artifact has the wrong shape: {path.name}")
    return value, {
        "path": logical_path or path.name,
        "sha256": _sha256_bytes(raw),
    }


def _manifest_analysis(
    records: list[SourceRecord], manifest: Any | None, metadata: dict[str, Any] | None
) -> dict[str, Any] | None:
    if manifest is None or metadata is None:
        return None
    manifest_ids: set[str] = set()
    malformed_records = 0
    for row in manifest:
        if not isinstance(row, dict) or not isinstance(row.get("product_id"), str):
            malformed_records += 1
            continue
        product_id = normalize_text(row["product_id"])
        if product_id:
            manifest_ids.add(product_id)
        else:
            malformed_records += 1
    csv_ids = {normalize_text(record.values["ID"]) for record in records}
    csv_ids.discard("")
    return {
        **metadata,
        "record_count": len(manifest),
        "malformed_record_count": malformed_records,
        "unique_product_id_count": len(manifest_ids),
        "csv_only_product_ids": sorted(csv_ids - manifest_ids),
        "manifest_only_product_ids": sorted(manifest_ids - csv_ids),
        "product_id_sets_match": csv_ids == manifest_ids,
        "relationship": "Image-level manifest keyed by the CSV product ID",
    }


def _source_metadata_analysis(
    value: Any | None, metadata: dict[str, Any] | None, parsed_rows: int
) -> dict[str, Any] | None:
    if value is None or metadata is None:
        return None
    return {
        **metadata,
        "declared_source": value.get("source"),
        "declared_dataset_version": value.get("dataset_version"),
        "declared_archive_sha256": value.get("archive_sha256"),
        "declared_product_records": value.get("product_records"),
        "declared_image_records": value.get("image_records"),
        "declared_product_count_matches_csv": value.get("product_records") == parsed_rows,
        "relationship": "Dataset acquisition provenance and declared aggregate counts",
    }


def _field_classifications(
    field_stats: dict[str, dict[str, Any]],
    product_ids: dict[str, Any],
    price: dict[str, Any],
    availability: dict[str, Any],
) -> list[dict[str, str]]:
    classifications: list[dict[str, str]] = []
    for field in field_stats:
        stats = field_stats[field]
        if field == "ID" and product_ids["conflicting_duplicate_group_count"]:
            readiness = "CONFLICTING DATA"
        elif field == "Price" and (price["parse_failure_count"] or price["negative_value_count"]):
            readiness = "REQUIRES VALIDATION"
        elif field == "Availability" and availability["mapping_assessment"] != (
            "production_values_match_exactly"
        ):
            readiness = "REQUIRES VALIDATION"
        elif field == "Product Name" and stats["text_length"]["minimum"] < 3:
            readiness = "REQUIRES VALIDATION"
        elif field == "Product Description" and stats["text_length"]["minimum"] < 20:
            readiness = "REQUIRES VALIDATION"
        elif stats["usable_value_count"] < stats["total_rows"]:
            readiness = "READY WITH MISSING VALUES"
        else:
            readiness = "READY"
        canonical_use = next(
            item["canonical_use"] for item in SOURCE_TO_CONTRACT if item["source_field"] == field
        )
        classifications.append({"field": field, "readiness": readiness, "note": canonical_use})
    classifications.extend(
        {
            "field": field,
            "readiness": "UNSUPPORTED BY FIXTURE",
            "note": "Not supplied; no inference permitted",
        }
        for field in UNSUPPORTED_PRODUCTION_FIELDS
    )
    return classifications


def audit_product_metadata(
    csv_path: Path,
    *,
    source_path: str,
    manifest_path: Path | None = None,
    manifest_source_path: str | None = None,
    source_metadata_path: Path | None = None,
    source_metadata_source_path: str | None = None,
) -> dict[str, Any]:
    headers, records, source = _read_csv(csv_path)
    mapping_by_field = {item["source_field"]: item for item in SOURCE_TO_CONTRACT}
    unmapped_columns = sorted(set(headers) - set(mapping_by_field))
    if unmapped_columns:
        raise MetadataAuditError(
            f"Source columns lack an explicit production mapping: {', '.join(unmapped_columns)}"
        )
    field_stats = {
        field: _field_statistics(field, records, field in TEXT_COLUMNS) for field in headers
    }
    product_ids, conflicting_ids = _product_id_integrity(headers, records)
    price = _price_analysis(records)
    availability = _availability_analysis(records)

    invalid_semantic: dict[str, set[str]] = defaultdict(set)
    missing_id_rows: list[dict[str, Any]] = []
    for record in records:
        product_id = normalize_text(record.values["ID"])
        if not product_id:
            missing_id_rows.append({**_row_evidence(record), "reason": "missing_product_id"})
            continue
        if not normalize_text(record.values["Product Name"]):
            invalid_semantic[product_id].add("missing_product_name")
        if not normalize_text(record.values["Product Description"]):
            invalid_semantic[product_id].add("missing_product_description")
    quarantined_ids = set(conflicting_ids) | set(invalid_semantic)
    all_ids = {
        normalize_text(record.values["ID"])
        for record in records
        if normalize_text(record.values["ID"])
    }
    valid_ids = sorted(all_ids - quarantined_ids)
    quarantine = [
        {
            "product_id": product_id,
            "reasons": sorted(
                invalid_semantic.get(product_id, set())
                | ({"conflicting_duplicate_records"} if product_id in conflicting_ids else set())
            ),
        }
        for product_id in sorted(quarantined_ids)
    ]

    manifest_value, manifest_metadata = _metadata_relationship(
        manifest_path, manifest_source_path, list
    )
    source_metadata_value, source_metadata_metadata = _metadata_relationship(
        source_metadata_path, source_metadata_source_path, dict
    )
    manifest_analysis = _manifest_analysis(records, manifest_value, manifest_metadata)
    provenance_analysis = _source_metadata_analysis(
        source_metadata_value, source_metadata_metadata, len(records)
    )

    name_short = [
        {**_row_evidence(record), "product_id": normalize_text(record.values["ID"])}
        for record in records
        if 0 < len(normalize_text(record.values["Product Name"])) < 3
    ]
    description_short = [
        {**_row_evidence(record), "product_id": normalize_text(record.values["ID"])}
        for record in records
        if 0 < len(normalize_text(record.values["Product Description"])) < 20
    ]
    compound_colors = Counter(
        normalize_text(record.values["Color"])
        for record in records
        if normalize_text(record.values["Color"])
        and COMPOUND_COLOR_PATTERN.search(normalize_text(record.values["Color"]))
    )
    normalization_collision_count = sum(
        stats["normalization_impact"]["collision_group_count"] for stats in field_stats.values()
    )
    classifications = _field_classifications(field_stats, product_ids, price, availability)
    blockers: list[str] = []
    if not valid_ids:
        blockers.append("No valid product IDs can instantiate product-text-v1")
    if product_ids["conflicting_duplicate_group_count"]:
        blockers.append("Conflicting duplicate IDs must be quarantined by the builder")
    if field_stats["Product Name"]["usable_value_count"] == 0:
        blockers.append("Product Name has no usable values")
    if field_stats["Product Description"]["usable_value_count"] == 0:
        blockers.append("Product Description has no usable values")

    payload: dict[str, Any] = {
        "audit_version": AUDIT_VERSION,
        "contract": {
            "adr": ADR_PATH,
            "status": "LOCKED",
            "document_version": DOCUMENT_VERSION,
            "semantic_fields": ["Product Name", "Product Description", "Color"],
            "semantic_field_ownership": {
                "Product Name": "Product",
                "Product Description": "Product",
                "Color": "ProductVariant",
            },
            "structured_listing_fields": [
                "Price",
                "Currency",
                "Availability",
            ],
            "structured_inventory_fields": ["Stock quantity"],
            "fixture_variant_policy": {
                "variants_per_product": 1,
                "variant_code": "default",
                "color_source": "Color",
                "size": None,
                "inference_performed": False,
            },
            "forbidden_inferences": list(UNSUPPORTED_PRODUCTION_FIELDS),
        },
        "source": {**source, "path": source_path},
        "related_artifacts": {
            "manifest": manifest_analysis,
            "source_metadata": provenance_analysis,
        },
        "source_to_contract_mapping": list(SOURCE_TO_CONTRACT),
        "unsupported_production_fields": [
            {
                "field": field,
                "readiness": "UNSUPPORTED BY FIXTURE",
                "policy": "remain missing; no inference permitted",
            }
            for field in UNSUPPORTED_PRODUCTION_FIELDS
        ],
        "field_statistics": field_stats,
        "semantic_field_analysis": {
            "product_name": {
                "extremely_short_threshold": "normalized length < 3",
                "extremely_short_values": name_short,
            },
            "product_description": {
                "extremely_short_threshold": "normalized length < 20",
                "extremely_short_values": description_short,
            },
            "color": {
                "ontology_conversion_performed": False,
                "distinct_raw_values": sorted(
                    {
                        record.values["Color"]
                        for record in records
                        if normalize_text(record.values["Color"])
                    }
                ),
                "compound_or_free_text_values": [
                    {"value": value, "count": count}
                    for value, count in sorted(compound_colors.items())
                ],
            },
        },
        "product_id_integrity": product_ids,
        "price_analysis": price,
        "availability_analysis": availability,
        "normalization_impact": {
            "policy_reference": ADR_PATH,
            "analysis_only": True,
            "semantic_rewriting_performed": False,
            "field_impacts": {
                field: stats["normalization_impact"] for field, stats in field_stats.items()
            },
            "total_collision_group_count": normalization_collision_count,
        },
        "exclusions_and_quarantine": {
            "valid_canonical_document_candidate_count": len(valid_ids),
            "valid_canonical_document_product_ids": valid_ids,
            "quarantined_product_id_count": len(quarantine),
            "quarantined_products": quarantine,
            "rows_without_product_id_count": len(missing_id_rows),
            "rows_without_product_id": missing_id_rows,
        },
        "contract_fitness": {
            "field_classifications": classifications,
            "can_produce_one_document_per_valid_product_id": bool(valid_ids),
            "optional_sparse_fields": [
                field
                for field in ("Color",)
                if field_stats[field]["usable_value_count"] < len(records)
            ],
            "usable_listing_fields": [
                field
                for field, ready in (
                    (
                        "Price",
                        not price["parse_failure_count"] and not price["negative_value_count"],
                    ),
                    ("Availability", availability["coverage_percentage"] == 100.0),
                )
                if ready
            ],
            "absent_production_fields": list(UNSUPPORTED_PRODUCTION_FIELDS),
            "blockers_for_adr_ml_004": blockers,
            "overall_readiness_verdict": "GREEN" if valid_ids else "RED",
        },
        "reproducibility": {
            "generated_timestamp_included": False,
            "timestamp_policy": "Omitted so identical source bytes produce identical evidence",
            "percentile_policy": "nearest-rank",
            "synthetic_fixture_used_as_benchmark_evidence": False,
        },
    }
    return {**payload, "evidence_sha256": f"sha256:{_content_hash(payload)}"}


def _markdown_cell(value: Any) -> str:
    if value is None:
        return "—"
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def render_markdown(audit: dict[str, Any]) -> str:
    source = audit["source"]
    ids = audit["product_id_integrity"]
    exclusions = audit["exclusions_and_quarantine"]
    price = audit["price_analysis"]
    availability = audit["availability_analysis"]
    fitness = audit["contract_fitness"]
    fields = audit["field_statistics"]
    delimiter = _markdown_cell(source["delimiter"])
    quote_character = _markdown_cell(source["quote_character"])
    physical_rows = source["physical_rows"]
    physical_lines = source["physical_lines_including_header"]
    lines = [
        "# Khaadi contract-mapping metadata audit",
        "",
        f"Gate 1 status: **{fitness['overall_readiness_verdict']}**.",
        "",
        "Khaadi is an evaluation fixture. PostgreSQL remains the production source of truth,",
        "and no missing Product, ProductVariant, Listing, or Inventory attribute was inferred.",
        "Each Khaadi product maps to one default variant. Price and availability are",
        "audited only as structured Listing metadata and are excluded from canonical text.",
        "",
        "## Source identity",
        "",
        f"- CSV: `{source['path']}`",
        f"- SHA-256: `{source['sha256']}`",
        f"- Encoding: `{source['encoding']}`; BOM: `{str(source['has_byte_order_mark']).lower()}`",
        f"- Delimiter: `{delimiter}`; quote: `{quote_character}`",
        f"- Physical rows excluding header: **{physical_rows:,}** "
        f"({physical_lines:,} lines including header)",
        f"- Parsed rows: **{source['parsed_rows']:,}**",
        f"- Exact columns: {', '.join(f'`{column}`' for column in source['columns'])}",
        "",
    ]
    manifest = audit["related_artifacts"]["manifest"]
    if manifest:
        lines.extend(
            [
                "The image manifest is an image-level artifact keyed by CSV product ID: "
                f"{manifest['record_count']:,} image records, "
                f"{manifest['unique_product_id_count']:,} product IDs, and "
                f"product-ID sets match = **{str(manifest['product_id_sets_match']).lower()}**.",
                "",
            ]
        )
    source_metadata = audit["related_artifacts"]["source_metadata"]
    if source_metadata:
        declared_count = source_metadata["declared_product_records"]
        count_matches = source_metadata["declared_product_count_matches_csv"]
        lines.extend(
            [
                "The source metadata identifies the acquisition provenance and declares "
                f"{declared_count:,} product records; parsed-count match = "
                f"**{str(count_matches).lower()}**.",
                "",
            ]
        )
    lines.extend(
        [
            "## Source-to-production mapping",
            "",
            "| Khaadi field | Production owner | Canonical use |",
            "| --- | --- | --- |",
        ]
    )
    for item in audit["source_to_contract_mapping"]:
        source_field = _markdown_cell(item["source_field"])
        owner = _markdown_cell(item["production_owner"])
        canonical_use = _markdown_cell(item["canonical_use"])
        lines.append(f"| {source_field} | {owner} | {canonical_use} |")
    lines.extend(
        [
            "",
            "Currency, stock quantity, brand, category, tags, materials, gender, and product",
            "type are **UNSUPPORTED BY FIXTURE** and remain missing. Category and brand remain",
            "valid vendor-provided production fields; they are not inferred from Khaadi.",
            "",
            "## Field quality",
            "",
            "Distinct counts and lengths use usable values. p95 length uses nearest-rank.",
            "",
            "| Field | Rows | Null | Blank | Whitespace-only | Usable | Coverage | "
            "Distinct raw / normalized | Length min / median / p95 / max |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for field in source["columns"]:
        stats = fields[field]
        length = stats["text_length"]
        length_text = "n/a"
        if length:
            length_text = (
                f"{length['minimum']} / {length['median']} / "
                f"{length['p95_nearest_rank']} / {length['maximum']}"
            )
        lines.append(
            f"| {_markdown_cell(field)} | {stats['total_rows']} | {stats['null_count']} | "
            f"{stats['blank_string_count']} | {stats['whitespace_only_count']} | "
            f"{stats['usable_value_count']} | {stats['usable_coverage_percentage']:.2f}% | "
            f"{stats['distinct_value_count']} / {stats['normalized_distinct_value_count']} | "
            f"{length_text} |"
        )
    lines.extend(
        [
            "",
            "### Duplicate, placeholder, and sample evidence",
            "",
            "| Field | Duplicate groups | Duplicate rows beyond first | Placeholder values | "
            "Representative samples |",
            "| --- | ---: | ---: | ---: | --- |",
        ]
    )
    for field in source["columns"]:
        stats = fields[field]
        duplicates = stats["duplicate_values"]
        placeholder_count = len(stats["suspicious_placeholder_values"])
        samples = "; ".join(
            _markdown_cell(value)[:80] for value in stats["representative_value_samples"][:3]
        )
        lines.append(
            f"| {_markdown_cell(field)} | {duplicates['group_count']} | "
            f"{duplicates['duplicate_row_count_beyond_first']} | {placeholder_count} | "
            f"{samples} |"
        )
    semantic = audit["semantic_field_analysis"]
    name_short_count = len(semantic["product_name"]["extremely_short_values"])
    description_short_count = len(semantic["product_description"]["extremely_short_values"])
    color_values = ", ".join(semantic["color"]["distinct_raw_values"])
    compound_color_count = len(semantic["color"]["compound_or_free_text_values"])
    lines.extend(
        [
            "",
            "### Semantic-field diagnostics",
            "",
            f"- Product names below 3 normalized characters: **{name_short_count}**",
            f"- Product descriptions below 20 normalized characters: **{description_short_count}**",
            f"- Product Name exact duplicate groups: "
            f"**{fields['Product Name']['duplicate_values']['group_count']}**",
            f"- Product Description exact duplicate groups: "
            f"**{fields['Product Description']['duplicate_values']['group_count']}**",
            f"- Meaningful non-ASCII Product Name / Description values: "
            f"**{fields['Product Name']['meaningful_unicode_value_count']} / "
            f"{fields['Product Description']['meaningful_unicode_value_count']}**",
            f"- Color coverage: **{fields['Color']['usable_coverage_percentage']:.2f}%**; "
            f"raw distinct values: **{fields['Color']['distinct_value_count']}**; "
            f"compound/free-text forms: **{compound_color_count}**",
            f"- Distinct raw colors (no ontology applied): {color_values}",
            "",
        ]
    )
    missing_ids = ids["missing_id_count"]
    blank_ids = ids["blank_id_count"]
    whitespace_ids = ids["whitespace_only_id_count"]
    identical_duplicates = ids["identical_duplicate_group_count"]
    conflicting_duplicates = ids["conflicting_duplicate_group_count"]
    valid_candidates = exclusions["valid_canonical_document_candidate_count"]
    lines.extend(
        [
            "",
            "## Product ID integrity",
            "",
            f"- Unique product IDs: **{ids['unique_product_id_count']:,}**",
            f"- Missing/blank/whitespace-only IDs: "
            f"**{missing_ids} / {blank_ids} / {whitespace_ids}**",
            f"- Duplicate ID groups: **{ids['duplicate_id_group_count']}**",
            f"- Identical duplicate groups: **{identical_duplicates}** "
            "(deterministic deduplication candidates)",
            f"- Conflicting duplicate groups: **{conflicting_duplicates}** (quarantine candidates)",
            f"- Valid canonical-document candidates: **{valid_candidates:,}**",
            f"- Quarantined product IDs: **{exclusions['quarantined_product_id_count']}**",
            "",
        ]
    )
    if ids["conflicting_duplicate_groups"]:
        lines.extend(
            [
                "### Conflicting duplicate records",
                "",
                "| Product ID | Source lines | Conflicting fields |",
                "| --- | --- | --- |",
            ]
        )
        for group in ids["conflicting_duplicate_groups"]:
            source_lines = ", ".join(
                str(record["source_line_start"]) for record in group["records"]
            )
            conflicting_fields = ", ".join(field["field"] for field in group["conflicting_fields"])
            product_id = _markdown_cell(group["product_id"])
            conflict_text = _markdown_cell(conflicting_fields)
            lines.append(f"| {product_id} | {source_lines} | {conflict_text} |")
        lines.append("")
    parse_success = price["parse_success_count"]
    parse_percentage = price["parse_success_percentage_of_all_rows"]
    parse_failures = price["parse_failure_count"]
    negative_prices = price["negative_value_count"]
    zero_prices = price["zero_value_count"]
    price_range = f"{price['minimum']} / {price['median']} / {price['maximum']}"
    lines.extend(
        [
            "## Price (structured Listing metadata only)",
            "",
            f"Raw values are `{price['source_data_type']}`. "
            "Currency inference was **not** performed.",
            "",
            f"- Parse success: **{parse_success:,}/{source['parsed_rows']:,} "
            f"({parse_percentage:.2f}%)**",
            f"- Parse failures: **{parse_failures}**; negative: **{negative_prices}**; "
            f"zero: **{zero_prices}**",
            f"- Minimum / median / maximum: **{price_range}**",
            "",
            "## Availability (structured Listing metadata only)",
            "",
            f"Coverage: **{availability['coverage_percentage']:.2f}%**. No mapping was applied.",
            "",
            "| Raw value | Count | Analysis-only candidate |",
            "| --- | ---: | --- |",
        ]
    )
    for value, count in availability["raw_frequencies"].items():
        rendered_value = _markdown_cell(value)
        candidate = _markdown_cell(availability["candidate_mapping_not_applied"][value])
        lines.append(f"| {rendered_value} | {count} | `{candidate}` |")
    mapping_assessment = availability["mapping_assessment"]
    lines.extend(
        [
            "",
            f"Mapping assessment: **{mapping_assessment}**. Candidate spellings are evidence "
            "only and require an explicit mapping policy before ingestion.",
            "",
            "## Normalization impact",
            "",
            "Normalization was evaluated in analysis mode only: Unicode NFKC, control-character",
            "removal, outer trimming, and repeated-whitespace collapse. No semantic rewriting,",
            "translation, correction, enrichment, or ontology conversion was performed.",
            "",
            "| Field | Unicode | Controls | Trim | Whitespace collapse | Any change | "
            "Collision groups |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for field in source["columns"]:
        impact = fields[field]["normalization_impact"]
        lines.append(
            f"| {_markdown_cell(field)} | {impact['unicode_normalization_value_count']} | "
            f"{impact['control_character_removal_value_count']} | "
            f"{impact['outer_whitespace_trimming_value_count']} | "
            f"{impact['repeated_whitespace_collapse_value_count']} | "
            f"{impact['any_change_value_count']} | {impact['collision_group_count']} |"
        )
    collision_count = audit["normalization_impact"]["total_collision_group_count"]
    lines.extend(
        [
            "",
            f"Total normalization collision groups across source fields: **{collision_count}**.",
            "",
            "## Contract fitness",
            "",
            "| Field | Classification | Note |",
            "| --- | --- | --- |",
        ]
    )
    for item in fitness["field_classifications"]:
        field_name = _markdown_cell(item["field"])
        readiness = item["readiness"]
        note = _markdown_cell(item["note"])
        lines.append(f"| {field_name} | **{readiness}** | {note} |")
    blocker_text = (
        "; ".join(fitness["blockers_for_adr_ml_004"])
        if fitness["blockers_for_adr_ml_004"]
        else "None"
    )
    quarantined_count = exclusions["quarantined_product_id_count"]
    missing_id_row_count = exclusions["rows_without_product_id_count"]
    sparse_fields = ", ".join(fitness["optional_sparse_fields"]) or "none"
    listing_fields = ", ".join(fitness["usable_listing_fields"]) or "none"
    absent_fields = ", ".join(fitness["absent_production_fields"])
    lines.extend(
        [
            "",
            "## Conclusion",
            "",
            f"1. One semantic document can be produced for **{valid_candidates:,}** valid "
            "product IDs.",
            f"2. **{quarantined_count}** product IDs require quarantine; "
            f"**{missing_id_row_count}** rows lack an addressable product ID.",
            f"3. Sparse optional fields: **{sparse_fields}**.",
            f"4. Usable Listing fields: **{listing_fields}**; availability aliases still "
            "require an explicit mapping policy where noted.",
            f"5. Completely absent production fields: **{absent_fields}**.",
            f"6. Blockers for ADR-ML-004 implementation: **{_markdown_cell(blocker_text)}**.",
            "",
            "No generation timestamp is embedded so repeated runs over identical inputs are",
            "byte-for-byte deterministic. Machine-readable counts and evidence are stored in",
            "`artifacts/product_metadata_audit/product_metadata_audit.json`.",
            "",
            f"Evidence checksum: `{audit['evidence_sha256']}`.",
            "",
        ]
    )
    return "\n".join(lines)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        os.replace(temporary_name, path)
    finally:
        Path(temporary_name).unlink(missing_ok=True)


def write_audit_artifacts(audit: dict[str, Any], json_path: Path, report_path: Path) -> None:
    json_content = (
        json.dumps(audit, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
    )
    _atomic_write(json_path, json_content)
    _atomic_write(report_path, render_markdown(audit))
