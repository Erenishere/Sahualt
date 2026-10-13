"""Export verified frozen product-text-v1 rows for exhaustive human judging (no retrieval)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sahulat_text.documents.corpus import DEFAULT_REGISTRY
from sahulat_text.documents.projection import DocumentContractError
from sahulat_text.evaluation.judging_export import (
    export_error_message,
    export_judging_products_csv,
    format_export_report,
)
from sahulat_text.evaluation.protocol import TextEvaluationError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only CSV export of frozen product-text-v1 for human judging"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/eval_text_v1/judging_products.csv"),
        help="Destination CSV path",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=DEFAULT_REGISTRY,
        help="Frozen corpus registry (default: configs/corpora/product_text_v1.json)",
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path("."),
        help="Repository root for relative corpus paths",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing output file",
    )
    parser.add_argument(
        "--skip-protocol-bind",
        action="store_true",
        help="Verify registry/corpus only; do not cross-check EVAL-TEXT-V1 protocol",
    )
    args = parser.parse_args(argv)
    try:
        summary = export_judging_products_csv(
            args.output,
            repository_root=args.repository_root,
            registry_path=args.registry if args.skip_protocol_bind else None,
            overwrite=args.overwrite,
            bind_eval_protocol=not args.skip_protocol_bind,
        )
    except (TextEvaluationError, DocumentContractError) as error:
        print(export_error_message(error), file=sys.stderr)
        return 1
    print(format_export_report(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
