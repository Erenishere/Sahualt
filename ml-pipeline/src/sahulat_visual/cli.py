import argparse
import json
import sys
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

from .config import Settings
from .dataset import audit_dataset, freeze_split, read_manifest, records_from_audit
from .domain import positive_k
from .encoders.factory import create_encoder
from .errors import EmptyIndexError, VisualError
from .evaluation.comparison import compare
from .evaluation.protocol import audit_protocol, config_path, load_protocol
from .evaluation.runner import benchmark
from .index import InMemoryVectorIndex
from .io import write_json
from .logging import configure_logging
from .pipeline import embed_catalogue
from .retrieval import VisualRetrievalService


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Sahulat AI visual retrieval")
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("audit-dataset", "freeze-eval", "benchmark-visual"):
        command = commands.add_parser(name)
        command.add_argument("--config", type=Path, default=Path("configs/eval_visual_v1.yaml"))
        command.add_argument("--output", type=Path, required=True)
        if name == "benchmark-visual":
            command.add_argument("--model", choices=["openclip", "fashionclip"])
            command.add_argument("--device")
    build = commands.add_parser("build-visual-index")
    build.add_argument("--manifest", type=Path, required=True)
    build.add_argument("--root", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--dataset-version", required=True)
    build.add_argument("--model", choices=["openclip", "fashionclip"])
    build.add_argument("--device")
    query = commands.add_parser("query-image")
    query.add_argument("--index", type=Path, required=True)
    query.add_argument("--image", type=Path, required=True)
    query.add_argument("--top-k", type=int)
    query.add_argument("--model", choices=["openclip", "fashionclip"])
    query.add_argument("--device")
    comparison = commands.add_parser("compare-models")
    comparison.add_argument("--openclip", type=Path, required=True)
    comparison.add_argument("--fashionclip", type=Path, required=True)
    comparison.add_argument(
        "--output", type=Path, default=Path("reports/visual_model_comparison.md")
    )
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    configure_logging()
    try:
        if args.command in {"audit-dataset", "freeze-eval"}:
            config = load_protocol(args.config)
            audit = audit_protocol(config, args.config)
            write_json(args.output, audit)
            summary = {
                k: v
                for k, v in audit.items()
                if k
                not in {"retained", "excluded", "binary_duplicate_groups", "pixel_duplicate_groups"}
            }
            if args.command == "freeze-eval":
                split = freeze_split(
                    config_path(args.config, config["split"]["artifact"]), audit, config
                )
                summary["split"] = split["statistics"]
                summary["split_sha256"] = split["split_sha256"]
            print(json.dumps(summary, indent=2))
            return 0
        if args.command == "compare-models":
            compare(args.openclip, args.fashionclip, args.output)
            print(str(args.output))
            return 0
        settings = Settings.from_env()
        overrides = {key: getattr(args, key) for key in ("model", "device") if getattr(args, key)}
        settings = replace(settings, **overrides)
        if args.command == "benchmark-visual":
            result = benchmark(args.config, settings, args.output)
            print(json.dumps(result, indent=2))
        elif args.command == "build-visual-index":
            audit = audit_dataset(read_manifest(args.manifest), args.root)
            write_json(args.output.with_suffix(".audit.json"), audit)
            records = records_from_audit(audit)
            if not records:
                raise EmptyIndexError("No valid catalogue images remain after audit")
            encoder = create_encoder(settings)
            embedded = embed_catalogue(
                encoder,
                records,
                args.root,
                settings.batch_size,
                settings.num_workers,
                expected_hashes={r["image_id"]: r["pixel_sha256"] for r in audit["retained"]},
            )
            index = InMemoryVectorIndex(
                encoder.identity,
                embedded.vectors,
                records,
                {
                    "dataset_version": args.dataset_version,
                    "dataset_fingerprint": audit["retained_sha256"],
                    "created_at": datetime.now(UTC).isoformat(),
                    "embedding_ms": embedded.total_ms,
                },
            )
            index.save(args.output)
            print(json.dumps({"indexed_vectors": index.count, **encoder.identity.to_dict()}))
        elif args.command == "query-image":
            top_k = args.top_k if args.top_k is not None else settings.product_top_k
            positive_k(top_k)
            index = InMemoryVectorIndex.load(args.index)
            service = VisualRetrievalService(create_encoder(settings), index, settings.image_top_k)
            products = service.search(args.image, top_k)
            print(
                json.dumps(
                    {
                        "model": service.encoder.model_name,
                        "embedding_version": index.identity.embedding_version,
                        "results": [asdict(p) for p in products],
                    },
                    indent=2,
                )
            )
        return 0
    except (VisualError, OSError, ValueError) as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}), file=sys.stderr)
        return 2
