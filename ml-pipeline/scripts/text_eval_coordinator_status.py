"""Print EVAL-TEXT-V1 human-data gate status for the coordinator (no retrieval)."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from sahulat_text.evaluation.judging_export import export_error_message
from sahulat_text.evaluation.protocol import TextEvaluationError, load_text_protocol
from sahulat_text.evaluation.queries import DEFAULT_INPUT, query_status

DEFAULT_JUDGING_CSV = Path("data/eval_text_v1/judging_products.csv")
DEFAULT_OUTPUT_ROOT = Path("artifacts/eval_text_v1")


def _judging_csv_summary(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"present": False, "rows": 0, "unique_product_ids": 0}
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != [
            "row_number",
            "product_id",
            "name",
            "description",
            "color",
        ]:
            return {"present": True, "rows": -1, "unique_product_ids": 0, "invalid_header": True}
        rows = list(reader)
    product_ids = {row["product_id"] for row in rows}
    return {
        "present": True,
        "rows": len(rows),
        "unique_product_ids": len(product_ids),
        "invalid_header": False,
    }


def _frozen_queries_present(output_root: Path) -> bool:
    return (output_root / "queries.jsonl").exists() and (
        output_root / "queries.manifest.json"
    ).exists()


def _frozen_labels_present(output_root: Path) -> bool:
    return (output_root / "qrels.jsonl").exists() and (
        output_root / "labels.manifest.json"
    ).exists()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="EVAL-TEXT-V1 coordinator gate dashboard")
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--collection", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--judging-csv", type=Path, default=DEFAULT_JUDGING_CSV)
    args = parser.parse_args(argv)

    try:
        protocol = load_text_protocol(repository_root=args.repository_root)
        status = query_status(protocol, args.collection, args.output_root)
        judging = _judging_csv_summary(args.judging_csv)
    except TextEvaluationError as error:
        print(export_error_message(error), file=sys.stderr)
        return 1

    query_frozen = _frozen_queries_present(args.output_root)
    labels_frozen = _frozen_labels_present(args.output_root)
    corpus_ok = judging.get("present") and judging.get("rows") == len(protocol.product_ids)
    coverage = status.get("coverage") or {}
    queries_ready = coverage.get("requirements_pass") is True
    retriever_blocked = not labels_frozen

    lines = [
        "EVAL-TEXT-V1 coordinator status",
        "",
        f"Protocol: {protocol.version} / corpus {protocol.corpus_id}",
        f"Corpus products (protocol): {len(protocol.product_ids)}",
        "",
        "Gates:",
        "  product-text-v1 frozen corpus     OK (registered)",
        f"  judging_products.csv              {'OK' if corpus_ok else 'PENDING/INVALID'} "
        f"({judging.get('rows', 0)} rows, path={args.judging_csv})",
        f"  human queries collected           {status.get('query_count', 0)}/40",
        f"  query coverage valid              {'YES' if queries_ready else 'NO'}",
        f"  query dataset frozen              {'YES' if query_frozen else 'NO'}",
        f"  label dataset frozen              {'YES' if labels_frozen else 'NO'}",
        f"  retriever development             {'BLOCKED' if retriever_blocked else 'UNBLOCKED'}",
        "",
    ]
    issues = coverage.get("issues") or []
    if issues:
        lines.append("Coverage issues:")
        lines.extend(f"  - {issue}" for issue in issues)
        lines.append("")

    next_step = "Collect and freeze 40 genuine human queries (Stage A)."
    if query_frozen and not labels_frozen:
        next_step = "Complete 32,000 primary judgments (+ adjudication), then freeze-labels."
    elif labels_frozen:
        next_step = (
            "Human dataset frozen; build official EVAL-TEXT-V1 harness "
            "(Baselines A/B/D on frozen qrels)."
        )
    elif queries_ready and not query_frozen:
        next_step = "Run validate-queries, freeze-queries, verify-queries."

    lines.append(f"Next: {next_step}")
    print("\n".join(lines))
    print(json.dumps(status, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
