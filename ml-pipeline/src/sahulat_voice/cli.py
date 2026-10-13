import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from .adapters import create_adapter
from .audio import MAX_AUDIO_BYTES, MAX_AUDIO_FRAMES, MIN_AUDIO_FRAMES, SAMPLE_RATE
from .contracts import MODEL_SPECS, Language, RuntimeSettings
from .errors import ErrorCode, VoiceError
from .evaluation import load_evaluation_input
from .service import TranscriptionService
from .transcript import canonical_bytes


def _write(path: Path, record: object) -> None:
    try:
        encoded = canonical_bytes(record)
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(encoded)
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
    except (OSError, ValueError, UnicodeError):
        raise VoiceError(ErrorCode.IO_FAILED) from None


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Independent Sahulat speech-to-text (no search)")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "capabilities", help="Show pinned models, input limits and declared languages"
    )
    transcribe = commands.add_parser("transcribe")
    transcribe.add_argument("--audio", type=Path, required=True)
    transcribe.add_argument(
        "--language", choices=[language.value for language in Language], required=True
    )
    transcribe.add_argument("--model", choices=list(MODEL_SPECS), required=True)
    transcribe.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    transcribe.add_argument("--output", type=Path, required=True)
    transcribe.add_argument(
        "--allow-download",
        action="store_true",
        help="Explicit opt-in to downloading multi-GB pinned model weights",
    )
    validate = commands.add_parser("validate-evaluation-input")
    validate.add_argument("--manifest", type=Path, required=True)
    validate.add_argument("--audio-root", type=Path, required=True)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "capabilities":
            summary: dict[str, object] = {
                "gate": "VOICE-STT-FOUNDATION-V1",
                "languages": [language.value for language in Language],
                "language_selection": "caller_declared_not_detected",
                "audio": {
                    "format": "PCM WAV",
                    "channels": 1,
                    "bits": 16,
                    "sample_rate": SAMPLE_RATE,
                    "max_bytes": MAX_AUDIO_BYTES,
                    "min_seconds": MIN_AUDIO_FRAMES / SAMPLE_RATE,
                    "max_seconds": MAX_AUDIO_FRAMES / SAMPLE_RATE,
                },
                "models": {
                    name: {
                        "repository": spec.repository,
                        "revision": spec.revision,
                        "license": spec.license,
                    }
                    for name, spec in MODEL_SPECS.items()
                },
                "downloads": "disabled_by_default",
                "search": "NOT_IMPLEMENTED",
            }
        elif args.command == "validate-evaluation-input":
            summary = load_evaluation_input(args.manifest, args.audio_root).summary()
        else:
            observation = args.output.with_name(args.output.name + ".observation.json")
            if args.audio.resolve() in {args.output.resolve(), observation.resolve()}:
                raise VoiceError(ErrorCode.INVALID_CONFIG)
            try:
                with args.audio.open("rb") as stream:
                    payload = stream.read(MAX_AUDIO_BYTES + 1)
            except OSError:
                raise VoiceError(ErrorCode.IO_FAILED) from None
            adapter = create_adapter(
                args.model, RuntimeSettings(args.device, local_files_only=not args.allow_download)
            )
            result = TranscriptionService(adapter).transcribe(payload, args.language)
            _write(args.output, result.transcript.record())
            _write(observation, result.observation())
            summary = {
                "status": "TRANSCRIBED",
                "transcript_checksum": result.transcript.checksum,
                "audio_seconds": result.audio_duration_seconds,
                "total_ms": result.total_ms,
            }
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True, allow_nan=False))
        return 0
    except VoiceError as error:
        print(json.dumps({"status": "FAILED", "error": error.code.value}), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(json.dumps({"status": "FAILED", "error": ErrorCode.CANCELLED.value}), file=sys.stderr)
        return 130
    except (OSError, ValueError, RuntimeError):
        print(json.dumps({"status": "FAILED", "error": ErrorCode.IO_FAILED.value}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
