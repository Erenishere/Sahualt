import argparse
import json
from pathlib import Path

from sahulat_voice.corpora_v2.audit import audit_sources, status, verify_audit
from sahulat_voice.corpora_v2.registry import preregister, verify_protocol
from sahulat_voice.errors import VoiceError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare EVAL-VOICE-CORPORA-V2 source evidence")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("preregister")
    subparsers.add_parser("verify-protocol")
    audit = subparsers.add_parser("audit")
    audit.add_argument("--allow-network", action="store_true", required=True)
    subparsers.add_parser("verify-audit")
    subparsers.add_parser("status")
    args = parser.parse_args(argv)
    root = Path.cwd()
    try:
        if args.command == "preregister":
            result = preregister(root)
        elif args.command == "verify-protocol":
            result = verify_protocol(root)
        elif args.command == "audit":
            result = audit_sources(root)
        elif args.command == "verify-audit":
            result = verify_audit(root)
        else:
            result = status(root)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except VoiceError as error:
        print(json.dumps({"status": "FAILED", "error": error.code.value}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
