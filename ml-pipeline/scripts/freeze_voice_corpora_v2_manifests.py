"""Freeze and verify metadata-only EVAL-VOICE-CORPORA-V2 sample manifests."""

import argparse
import json
from pathlib import Path

from sahulat_voice.benchmark.io import read_canonical_json
from sahulat_voice.corpora_v2_manifest_freeze.freeze import (
    acquisition_blockers,
    freeze,
    require_acquisition_ready,
    verify_freeze,
)
from sahulat_voice.corpora_v2_manifest_freeze.protocol import preregister, verify_protocol
from sahulat_voice.errors import ErrorCode, VoiceError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("preregister")
    subparsers.add_parser("verify-protocol")
    freeze_parser = subparsers.add_parser("freeze")
    freeze_parser.add_argument("--allow-network", action="store_true", required=True)
    subparsers.add_parser("verify")
    acquisition = subparsers.add_parser("require-acquisition")
    acquisition.add_argument("source_id")
    args = parser.parse_args(argv)
    root = Path.cwd()
    try:
        if args.command == "preregister":
            result = preregister(root)
        elif args.command == "verify-protocol":
            result = verify_protocol(root)
        elif args.command == "freeze":
            result = freeze(root)
        elif args.command == "verify":
            result = verify_freeze(root)
        else:
            verify_freeze(root)
            gate = read_canonical_json(
                root / "configs/gates/eval_voice_corpora_v2_manifest_freeze.json"
            )
            source = gate["source_statuses"].get(args.source_id)
            if source is None:
                raise VoiceError(ErrorCode.INVALID_MANIFEST)
            blockers = acquisition_blockers(source, manifest_frozen=source["manifest_frozen"])
            require_acquisition_ready(source, manifest_frozen=source["manifest_frozen"])
            result = {
                "source_id": args.source_id,
                "status": "ACQUISITION_READY",
                "blockers": blockers,
            }
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except VoiceError as error:
        print(json.dumps({"status": "FAILED", "error": error.code.value}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
