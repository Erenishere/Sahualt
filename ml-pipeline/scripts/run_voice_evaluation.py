"""Offline model execution only; existing frozen data and adapters remain untouched."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Execute/verify the frozen CPU voice evaluation")
    parser.add_argument("command", choices=("run", "verify", "worker"))
    parser.add_argument("--model", choices=("whisper", "mms"))
    args = parser.parse_args(argv)
    root = Path.cwd()
    os.environ["HF_HOME"] = str(root / ".cache/voice/huggingface")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
    from sahulat_voice.benchmark.io import put_json, read_canonical_json, record_checksum
    from sahulat_voice.benchmark.protocol import ARTIFACT_PATH
    from sahulat_voice.errors import VoiceError
    from sahulat_voice.runs.execution import (
        acquired_assets,
        execute_model,
        verified_input,
        verify_model,
    )
    from sahulat_voice.transcript import canonical_bytes

    output = root / "artifacts/eval_voice_run_v1"
    try:
        resolved, corpus = output.resolve(), (root / ARTIFACT_PATH).resolve()
        if (
            not resolved.is_relative_to(root.resolve())
            or resolved.is_relative_to(corpus)
            or corpus.is_relative_to(resolved)
        ):
            print(json.dumps({"status": "FAILED", "error": "invalid_output_boundary"}))
            return 1
        descriptor, _ = verified_input(root)
        started = {"run_version": "eval-voice-run-v1", "dataset": descriptor}
        if args.command == "worker":
            if args.model is None:
                parser.error("worker requires --model")
            if read_canonical_json(output / "execution.started.json") != started:
                print(json.dumps({"status": "FAILED", "error": "execution_identity_mismatch"}))
                return 1
            execute_model(root, output / f"{args.model}.json", args.model)
            return 0
        if args.model is not None:
            parser.error(
                "--model is reserved for an internal worker; run/verify require both models"
            )
        models = ["whisper", "mms"]
        if args.command == "run":
            # Refuse a repeated run/checkpoint; verification is the only unchanged-run operation.
            if any(
                (output / f"{name}.json").exists() or (output / name).exists() for name in models
            ):
                print(json.dumps({"status": "FAILED", "error": "existing_execution_evidence"}))
                return 1
            for name in models:
                acquired_assets(root, name, check_cache=True)
            output.mkdir(parents=True, exist_ok=True)
            # Keep the exclusive marker after crashes to prevent another scored attempt.
            with (output / "execution.started.json").open("xb") as stream:
                stream.write(canonical_bytes(started))
            for name in models:
                completed = subprocess.run(
                    [sys.executable, str(Path(__file__).resolve()), "worker", "--model", name],
                    check=False,
                )
                if completed.returncode != 0:
                    print(json.dumps({"status": "FAILED", "error": "worker_failed", "model": name}))
                    return 1
        results = [verify_model(root, output / f"{name}.json", name) for name in models]
        if read_canonical_json(output / "execution.started.json") != started:
            print(json.dumps({"status": "FAILED", "error": "execution_identity_mismatch"}))
            return 1
        manifest = {"run_version": "eval-voice-run-v1", "dataset": descriptor, "models": results}
        complete_manifest = {**manifest, "manifest_checksum": record_checksum(manifest)}
        if args.command == "run":
            put_json(output / "manifest.json", complete_manifest)
        elif read_canonical_json(output / "manifest.json") != complete_manifest:
            print(json.dumps({"status": "FAILED", "error": "manifest_checksum_mismatch"}))
            return 1
        print(json.dumps({"status": "EVIDENCE_VERIFIED", "models": results}, sort_keys=True))
        return 0
    except VoiceError as error:
        print(json.dumps({"status": "FAILED", "error": error.code.value}))
        return 1
    except (OSError, ValueError, KeyError, TypeError):
        print(json.dumps({"status": "FAILED", "error": "invalid_or_unavailable_evidence"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
