"""Validate and freeze genuine human Sindhi recordings; never creates speech or references."""

import argparse
import json
from pathlib import Path

from sahulat_voice.alternatives import sindhi_holdout_v1 as holdout
from sahulat_voice.benchmark.io import read_json
from sahulat_voice.errors import VoiceError

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/sindhi_holdout_v1"
REGISTRY = ROOT / "configs/corpora/sindhi_holdout_v1.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("status", "validate", "freeze", "verify"))
    parser.add_argument("--input", type=Path)
    parser.add_argument("--audio-root", type=Path)
    args = parser.parse_args()
    if args.command not in {"status", "verify"} and (args.input is None or args.audio_root is None):
        parser.error("validate/freeze require --input and --audio-root")
    try:
        if args.command == "status":
            result = {
                "tooling_status": "GREEN",
                "dataset_status": "PENDING",
                "unique_utterance_count": 0,
                "recording_count": 0,
                "speaker_count": 0,
                "model_evaluation": "NOT_RUN",
            }
        elif args.command == "verify":
            result = holdout.verify(OUTPUT, REGISTRY)
        else:
            assert args.input is not None and args.audio_root is not None
            if args.command == "freeze":
                result = holdout.freeze(args.input, args.audio_root, OUTPUT, REGISTRY)
            else:
                validated = holdout.validate(read_json(args.input), args.audio_root)
                result = {
                    "status": "VALIDATED_NOT_FROZEN" if validated["complete"] else "PENDING",
                    "unique_utterance_count": len(validated["utterances"]),
                    "recording_count": len(validated["recordings"]),
                    "speaker_count": len(validated["speakers"]),
                }
        print(json.dumps(result))
        return 0
    except VoiceError as error:
        print(json.dumps({"status": "FAILED", "error": error.code.value}))
    except Exception as error:
        print(json.dumps({"status": "FAILED", "error_type": type(error).__name__}))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
