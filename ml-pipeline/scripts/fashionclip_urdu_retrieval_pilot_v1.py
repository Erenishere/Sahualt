from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sahulat_visual.io import read_json, write_json  # noqa: E402
from sahulat_visual.urdu_retrieval_pilot_v1 import (  # noqa: E402
    MODEL_NAMES,
    PILOT_ROOT,
    QUERY_DATA,
    PilotBlockedError,
    build_index,
    compare_translation_adapter,
    ensure_query_template,
    evaluate,
    freeze_query_manifest,
    load_authority,
    pilot_config,
    repository_root,
    search,
    status,
    validate_queries,
    verify_artifact_integrity,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Local-only FashionCLIP Urdu retrieval pilot; no production endpoints changed."
    )
    parser.add_argument("--root", type=Path, default=repository_root())
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("init", help="Create the 30-entry human-annotation template if missing")
    commands.add_parser(
        "status", help="Check local source, checkpoint, index, and annotation gates"
    )
    commands.add_parser("verify", help="Verify available pilot index checksums")

    build = commands.add_parser("build-index", help="Build separate local image indexes")
    build.add_argument("--models", nargs="+", choices=MODEL_NAMES, default=list(MODEL_NAMES))
    build.add_argument("--device", default="auto")

    validate = commands.add_parser("validate-queries", help="Validate annotation completion")
    validate.add_argument("--file", type=Path, default=None)

    commands.add_parser("export-products", help="Export Khaadi product IDs for human judging")
    commands.add_parser("freeze-queries", help="Freeze verified queries and relevance labels")

    run = commands.add_parser(
        "evaluate", help="Run English-reference and direct-Urdu retrieval tracks"
    )
    run.add_argument("--models", nargs="+", choices=MODEL_NAMES, default=list(MODEL_NAMES))

    adapter = commands.add_parser(
        "evaluate-translation", help="Evaluate separately configured local Urdu-to-English adapter"
    )
    adapter.add_argument("--model", choices=MODEL_NAMES, default="fashionclip")

    query = commands.add_parser("search", help="Run one exploratory query (not a benchmark result)")
    query.add_argument("--model", choices=MODEL_NAMES, default="fashionclip")
    query.add_argument("--urdu-query", required=True)
    query.add_argument("--english-query", default=None)

    serve = commands.add_parser("serve", help="Start standalone local demo API/UI")
    serve.add_argument("--model", choices=MODEL_NAMES, default="fashionclip")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)

    return parser


def _dump(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _annotation_file(args: argparse.Namespace, root: Path) -> Path:
    return args.file.resolve() if args.file else root / QUERY_DATA


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    args = _parser().parse_args()
    root = args.root.resolve()
    try:
        pilot_config(root)
        if args.command == "init":
            path = ensure_query_template(root)
            _dump({"status": "TEMPLATE_READY", "path": str(path.relative_to(root))})
        elif args.command == "status":
            _dump(status(root))
        elif args.command == "verify":
            _dump(verify_artifact_integrity(root))
        elif args.command == "build-index":
            _dump([build_index(model, root, args.device) for model in args.models])
        elif args.command == "validate-queries":
            authority = load_authority(root)
            path = _annotation_file(args, root)
            payload = read_json(path)
            errors = validate_queries(payload.get("queries"), authority.valid_product_ids)
            _dump(
                {
                    "status": "READY_TO_FREEZE" if not errors else "PENDING_HUMAN_ANNOTATIONS",
                    "file": str(path),
                    "query_count": len(payload.get("queries", [])),
                    "errors": errors,
                }
            )
            return 0 if not errors else 2
        elif args.command == "export-products":
            authority = load_authority(root)
            image_by_product: dict[str, str] = {}
            for row in authority.visual_retained:
                image_by_product.setdefault(row["product_id"], row["image_path"])
            export = []
            for row in authority.rows:
                product_id = row["ID"]
                if product_id not in authority.valid_product_ids:
                    continue
                export.append(
                    {
                        "product_id": product_id,
                        "product_name": row["Product Name"],
                        "description": row["Product Description"],
                        "price": row["Price"],
                        "color": row["Color"],
                        "sample_image_path": image_by_product.get(product_id),
                    }
                )
            path = root / PILOT_ROOT / "products_for_judging.json"
            write_json(path, export)
            _dump(
                {"status": "EXPORTED", "products": len(export), "path": str(path.relative_to(root))}
            )
        elif args.command == "freeze-queries":
            manifest = freeze_query_manifest(root)
            _dump(
                {
                    "status": "FROZEN",
                    "query_count": manifest["query_count"],
                    "manifest_sha256": manifest["manifest_sha256"],
                }
            )
        elif args.command == "evaluate":
            _dump(evaluate(root, args.models))
        elif args.command == "evaluate-translation":
            _dump(compare_translation_adapter(root, args.model))
        elif args.command == "search":
            _dump(search(args.model, args.urdu_query, args.english_query, root))
        elif args.command == "serve":
            if args.host not in {"127.0.0.1", "localhost", "::1"}:
                raise PilotBlockedError("The experimental UI may bind to loopback addresses only")
            import uvicorn

            from sahulat_visual.urdu_pilot_api import create_app

            uvicorn.run(
                create_app(root, args.model), host=args.host, port=args.port, log_level="info"
            )
        return 0
    except PilotBlockedError as exc:
        print(
            json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 2
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(
            json.dumps({"status": "ERROR", "reason": str(exc)}, ensure_ascii=False), file=sys.stderr
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
