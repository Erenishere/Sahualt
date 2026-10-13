from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from sahulat_text.documents.artifacts import atomic_write
from sahulat_text.documents.serialization import canonical_json_bytes

from .artifacts import freeze_labels, freeze_queries, load_frozen_queries, write_readiness
from .labeling import validate_queries
from .protocol import (
    DEFAULT_CONFIG,
    DEFAULT_LOCK,
    load_text_protocol,
    preregister_protocol,
    verify_protocol_lock,
)
from .queries import DEFAULT_INPUT, import_queries, load_collection, query_status

QUERY_ACTIONS = {
    "import-queries",
    "validate-queries",
    "freeze-queries",
    "verify-queries",
    "query-status",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Pre-register text evaluation; human labels only")
    parser.add_argument(
        "action", choices=["preregister", "freeze-labels", "verify", *sorted(QUERY_ACTIONS)]
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--output-root", type=Path, default=Path("artifacts/eval_text_v1"))
    parser.add_argument("--report", type=Path, default=Path("reports/eval_text_v1_readiness.md"))
    parser.add_argument("--queries", type=Path)
    parser.add_argument("--collection", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--status-output", type=Path, help="Optional query-only evidence JSON")
    parser.add_argument("--judgments", type=Path)
    parser.add_argument("--adjudications", type=Path)
    args = parser.parse_args()
    try:
        protocol = load_text_protocol(args.config, repository_root=args.repository_root)
        if args.action == "preregister":
            preregister_protocol(protocol, args.lock)
        else:
            verify_protocol_lock(protocol, args.lock)
        if args.action in QUERY_ACTIONS:
            status_input = args.collection
            if args.judgments is not None or args.adjudications is not None:
                raise ValueError("query-only actions reject judgment/adjudication inputs")
            if (
                args.status_output is not None
                and args.status_output.name != "text-query-v1-status.json"
            ):
                raise ValueError(
                    "status output must be named text-query-v1-status.json, not data/policy files"
                )
            if args.action == "import-queries":
                if args.queries is None:
                    raise ValueError(
                        "--queries must contain actual human entries; none are generated"
                    )
                result = import_queries(protocol, args.queries, args.collection, args.output_root)
                print(json.dumps(result, sort_keys=True))
            elif args.action in {"validate-queries", "freeze-queries"}:
                source = args.queries if args.queries is not None else args.collection
                status_input = source
                queries = load_collection(protocol, source)
                validate_queries((query.record() for query in queries), protocol)
                if args.action == "freeze-queries":
                    freeze_queries(protocol, source, args.output_root)
                    # Verify the just-written bytes; no judging/readiness paths are invoked.
                    load_frozen_queries(protocol, args.output_root)
            elif args.action == "verify-queries":
                load_frozen_queries(protocol, args.output_root)
            status = query_status(protocol, status_input, args.output_root)
            if args.status_output is not None:
                atomic_write(args.status_output, canonical_json_bytes(status) + b"\n")
            print(json.dumps(status, sort_keys=True))
            return 0
        if args.action == "freeze-labels":
            if args.judgments is None:
                raise ValueError(
                    "--judgments must contain independent human labels; none will be generated"
                )
            freeze_labels(protocol, args.judgments, args.adjudications, args.output_root)
        readiness = write_readiness(protocol, args.output_root, args.report)
    except (ValueError, OSError, KeyError, TypeError, yaml.YAMLError) as error:
        print(f"EVAL-TEXT-V1: NOT READY; {error}")
        return 2
    print(
        f"EVAL-TEXT-V1 protocol: FROZEN; data: {readiness['stage']}; "
        f"corpus_products={readiness['product_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
