"""Read-only export of frozen product-text-v1 rows for human relevance judging."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from sahulat_text.documents.corpus import DEFAULT_REGISTRY, verify_registered_corpus
from sahulat_text.documents.projection import DocumentContractError

from .protocol import TextEvaluationError, TextEvaluationProtocol, load_text_protocol

CSV_COLUMNS = ("row_number", "product_id", "name", "description", "color")


@dataclass(frozen=True, slots=True)
class JudgingProductRow:
    row_number: int
    product_id: str
    name: str
    description: str
    color: str


def _canonical_product_id(value: str, *, position: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TextEvaluationError(f"corpus row {position}: missing product_id")
    try:
        canonical = str(UUID(value))
    except ValueError as error:
        raise TextEvaluationError(
            f"corpus row {position}: product_id must be a canonical UUID"
        ) from error
    if canonical != value:
        raise TextEvaluationError(
            f"corpus row {position}: product_id must be lowercase canonical UUID form"
        )
    return value


def load_judging_products_from_registry(
    registry: dict[str, Any], *, repository_root: Path
) -> tuple[JudgingProductRow, ...]:
    artifact_path = repository_root / str(registry["artifact_path"])
    payload = artifact_path.read_bytes()
    expected_count = registry["record_count"]
    if not isinstance(expected_count, int) or expected_count < 1:
        raise TextEvaluationError("registry record_count is invalid")

    rows: list[JudgingProductRow] = []
    seen: set[str] = set()
    for position, line in enumerate(payload.splitlines(), start=1):
        if not line.strip():
            raise TextEvaluationError(f"corpus row {position}: empty JSONL line")
        record = json.loads(line)
        if not isinstance(record, dict) or "fields" not in record:
            raise TextEvaluationError(f"corpus row {position}: invalid document record")
        fields = record["fields"]
        if not isinstance(fields, dict):
            raise TextEvaluationError(f"corpus row {position}: invalid fields object")
        product_id = _canonical_product_id(record.get("product_id", ""), position=position)
        if product_id in seen:
            raise TextEvaluationError(f"duplicate product_id in frozen corpus: {product_id}")
        seen.add(product_id)
        name = fields.get("name")
        description = fields.get("description")
        colors = fields.get("colors")
        if not isinstance(name, str) or not name.strip():
            raise TextEvaluationError(f"corpus row {position}: missing name")
        if not isinstance(description, str) or not description.strip():
            raise TextEvaluationError(f"corpus row {position}: missing description")
        if not isinstance(colors, list) or any(not isinstance(color, str) for color in colors):
            raise TextEvaluationError(f"corpus row {position}: invalid colors list")
        color = ", ".join(colors)
        rows.append(
            JudgingProductRow(
                row_number=len(rows) + 1,
                product_id=product_id,
                name=name,
                description=description,
                color=color,
            )
        )

    if len(rows) != expected_count:
        raise TextEvaluationError(
            f"product count mismatch: expected {expected_count}, found {len(rows)}"
        )
    ordered = tuple(sorted(rows, key=lambda row: row.product_id))
    return tuple(
        JudgingProductRow(index, row.product_id, row.name, row.description, row.color)
        for index, row in enumerate(ordered, start=1)
    )


def load_judging_products(
    *,
    repository_root: Path = Path("."),
    registry_path: Path = DEFAULT_REGISTRY,
    protocol: TextEvaluationProtocol | None = None,
) -> tuple[JudgingProductRow, ...]:
    registry = verify_registered_corpus(registry_path, repository_root=repository_root)
    rows = load_judging_products_from_registry(registry, repository_root=repository_root)
    if protocol is not None:
        if protocol.corpus_id != registry["corpus_id"]:
            raise TextEvaluationError("protocol corpus_id disagrees with frozen registry")
        if protocol.corpus_sha256 != registry["artifact_sha256"]:
            raise TextEvaluationError("protocol corpus checksum disagrees with frozen registry")
        corpus_ids = {row.product_id for row in rows}
        if protocol.product_ids != corpus_ids:
            raise TextEvaluationError("protocol product_id set disagrees with frozen corpus")
    return rows


def render_judging_products_csv(rows: tuple[JudgingProductRow, ...]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                "row_number": row.row_number,
                "product_id": row.product_id,
                "name": row.name,
                "description": row.description,
                "color": row.color,
            }
        )
    return buffer.getvalue().encode("utf-8")


def export_judging_products_csv(
    output: Path,
    *,
    repository_root: Path = Path("."),
    registry_path: Path | None = None,
    overwrite: bool = False,
    bind_eval_protocol: bool = True,
) -> dict[str, object]:
    if output.exists() and not overwrite:
        raise TextEvaluationError(f"output already exists: {output}; pass --overwrite to replace")

    protocol: TextEvaluationProtocol | None = None
    resolved_registry = registry_path or DEFAULT_REGISTRY
    if bind_eval_protocol:
        protocol = load_text_protocol(repository_root=repository_root)
        config_path = repository_root / "configs/eval_text_v1.yaml"
        resolved_registry = config_path.parent / protocol.settings["corpus"]["registry"]
    registry = verify_registered_corpus(resolved_registry, repository_root=repository_root)
    rows = load_judging_products(
        repository_root=repository_root,
        registry_path=resolved_registry,
        protocol=protocol,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(render_judging_products_csv(rows))

    return {
        "corpus_id": registry["corpus_id"],
        "schema_version": registry["schema_version"],
        "artifact_sha256": registry["artifact_sha256"],
        "product_count": len(rows),
        "unique_product_ids": len({row.product_id for row in rows}),
        "output": str(output),
    }


def format_export_report(summary: dict[str, object]) -> str:
    lines = [
        "product-text-v1 judging export",
        "",
        f"Corpus: {summary['schema_version']}",
        f"Products: {summary['product_count']}",
        f"Unique product IDs: {summary['unique_product_ids']}",
        f"Output: {summary['output']}",
        "",
        "PASS",
    ]
    return "\n".join(lines)


def export_error_message(error: BaseException) -> str:
    if isinstance(error, (TextEvaluationError, DocumentContractError)):
        return f"FAIL: {error}"
    return f"FAIL: {error}"
