"""Prepare the EVAL-VOICE-CORPORA-V2 audio-acquisition readiness gate."""

import argparse
import json
from pathlib import Path

from sahulat_voice.corpora_v2_readiness.analysis import (
    audit_readiness,
    status,
    verify_readiness,
)
from sahulat_voice.corpora_v2_readiness.protocol import preregister, verify_protocol
from sahulat_voice.errors import VoiceError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("preregister")
    subparsers.add_parser("verify-protocol")
    audit = subparsers.add_parser("audit")
    audit.add_argument("--allow-network", action="store_true", required=True)
    subparsers.add_parser("verify-readiness")
    subparsers.add_parser("status")
    args = parser.parse_args(argv)
    root = Path.cwd()
    try:
        if args.command == "preregister":
            result = preregister(root)
        elif args.command == "verify-protocol":
            result = verify_protocol(root)
        elif args.command == "audit":
            result = audit_readiness(root)
        elif args.command == "verify-readiness":
            result = verify_readiness(root)
        else:
            result = status(root)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except VoiceError as error:
        print(json.dumps({"status": "FAILED", "error": error.code.value}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
