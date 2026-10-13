"""Preregister/run/verify isolated specialist evidence without rerunning historical models."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["HF_HOME"] = str(ROOT / ".cache/voice/huggingface")
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

from sahulat_voice.alternatives import runner  # noqa: E402
from sahulat_voice.alternatives.metadata import OUTPUT  # noqa: E402
from sahulat_voice.benchmark.io import put_json, read_canonical_json, record_checksum  # noqa: E402
from sahulat_voice.errors import ErrorCode, VoiceError  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("preregister", "run", "verify", "worker"))
    args = parser.parse_args()
    try:
        if args.command == "preregister":
            runner.register(ROOT)
            print("EVAL-VOICE-ALT-V1: PREREGISTERED")
        elif args.command == "run":
            runner.verify_registration(ROOT)
            for key in runner.candidates(ROOT):
                runner.verified_assets(ROOT, key)
            if (ROOT / OUTPUT / "execution.started.json").exists():
                raise VoiceError(ErrorCode.INVALID_CONFIG)
            subprocess.run([sys.executable, __file__, "worker"], check=True, cwd=ROOT)
            evidence = runner.verify(ROOT)
            put_json(ROOT / OUTPUT / "validation.json", evidence)
            put_json(
                ROOT / runner.RESULT_REGISTRY, {"validation_sha256": record_checksum(evidence)}
            )
            print(json.dumps(evidence))
        elif args.command == "worker":
            import torch

            torch.set_num_threads(8)
            torch.set_num_interop_threads(8)
            runner.execute(ROOT)
        else:
            evidence = runner.verify(ROOT)
            if read_canonical_json(
                ROOT / OUTPUT / "validation.json"
            ) != evidence or read_canonical_json(ROOT / runner.RESULT_REGISTRY) != {
                "validation_sha256": record_checksum(evidence)
            }:
                raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
            print(json.dumps({"status": "EVIDENCE_VERIFIED", **evidence}))
        return 0
    except VoiceError as error:
        print(json.dumps({"status": "FAILED", "error": error.code.value}))
    except KeyboardInterrupt:
        print(json.dumps({"status": "INTERRUPTED;NO_AUTOMATIC_RESUME"}))
        return 130
    except Exception as error:
        print(json.dumps({"status": "FAILED", "error_type": type(error).__name__}))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
