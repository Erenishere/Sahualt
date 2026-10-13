import argparse
import json
import sys
from pathlib import Path
from time import monotonic

from ..errors import ErrorCode, VoiceError
from .dataset import freeze_subset, prepare_subset, verify_frozen
from .protocol import DATASET_ID, preregister, protocol_inputs, verify_protocol
from .source import acquire_asset, asset_from_record


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        description="FLEURS benchmark preparation only; no speech model execution"
    )
    root.add_argument("--repository-root", type=Path, default=Path.cwd())
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("preregister", "verify-protocol", "freeze", "verify"):
        commands.add_parser(name)
    acquire = commands.add_parser("acquire")
    acquire.add_argument("--source-root", type=Path)
    acquire.add_argument(
        "--allow-download",
        action="store_true",
        help="Explicitly acquire about 1.37 GB of pinned test-only archives",
    )
    acquire.add_argument("--metadata-only", action="store_true")
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--source-root", type=Path)
    return root


def _acquire(root: Path, source_root: Path, allow_download: bool, metadata_only: bool) -> None:
    verify_protocol(root)
    _, source = protocol_inputs(root)
    assets = [asset_from_record(source["card"])]
    for specification in source["languages"].values():
        assets.append(asset_from_record(specification["metadata"]))
        if not metadata_only:
            assets.append(asset_from_record(specification["archive"]))
    for asset in assets:
        if not allow_download and not (source_root / asset.path).exists():
            raise VoiceError(ErrorCode.IO_FAILED)
        last = monotonic()

        def progress(received: int, total: int, asset_path: str = asset.path) -> None:
            nonlocal last
            if received == total or monotonic() - last >= 5:
                print(
                    json.dumps(
                        {"asset": asset_path, "received_bytes": received, "expected_bytes": total}
                    ),
                    flush=True,
                )
                last = monotonic()

        acquire_asset(source_root, asset, source["revision"], progress)
        print(json.dumps({"asset": asset.path, "source_checksum": "VERIFIED"}), flush=True)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        root = args.repository_root.resolve()
        if args.command == "preregister":
            result = preregister(root)
        elif args.command == "verify-protocol":
            result = verify_protocol(root)
        elif args.command in ("acquire", "prepare"):
            _, source = protocol_inputs(root)
            location = args.source_root or root / ".cache/voice/fleurs" / source["revision"]
            source_root = location.resolve()
            if source_root == root or not source_root.is_relative_to(root):
                raise VoiceError(ErrorCode.INVALID_CONFIG)
            if args.command == "acquire":
                _acquire(root, source_root, args.allow_download, args.metadata_only)
                result = {"status": "ACQUIRED_CHECKSUM_VERIFIED", "model_results": "NOT_RUN"}
            else:
                result = prepare_subset(root, source_root)
        elif args.command == "freeze":
            result = freeze_subset(root)
        else:
            result = verify_frozen(root)
        summary = {
            "dataset_id": DATASET_ID,
            "command": args.command,
            "status": result.get("status", result.get("state", "FROZEN_PROTOCOL_ONLY")),
            "sample_count": result.get("sample_count"),
            "language_counts": result.get("language_counts"),
            "manifest_sha256": result.get("manifest_sha256"),
            "semantic_sha256": result.get("semantic_sha256"),
            "model_results": "NOT_RUN",
        }
        print(json.dumps(summary, sort_keys=True), flush=True)
        return 0
    except VoiceError as error:
        print(json.dumps({"status": "FAILED", "error": error.code.value}), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(json.dumps({"status": "FAILED", "error": ErrorCode.CANCELLED.value}), file=sys.stderr)
        return 130
    except Exception:
        # Public downloads can include signed redirects; never expose their exception URLs.
        print(json.dumps({"status": "FAILED", "error": ErrorCode.IO_FAILED.value}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
