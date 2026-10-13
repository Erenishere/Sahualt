import math
import os
from pathlib import Path
from time import perf_counter
from typing import Any

from ..benchmark.io import file_sha256, put_json, read_canonical_json, record_checksum
from ..benchmark.protocol import ARTIFACT_PATH
from ..contracts import NORMALIZATION_VERSION
from ..errors import ErrorCode, VoiceError
from ..evaluation import EvaluationSample, read_evaluation_audio
from ..runs.execution import (
    CaptureAdapter,
    environment,
    first_selected,
    model_identity_key,
    sample_call,
    verified_input,
)
from ..runs.scoring import distribution, score
from ..service import TranscriptionService
from ..transcript import build_transcript
from . import metadata
from .adapters import SpecialistWhisperAdapter
from .metadata import CONFIG, OUTPUT, candidates, spec, validate_official, verified_assets

KEY = os.environ.get("SAHULAT_VOICE_ALT_KEY", "pashto-ghag")
TARGET_LANGUAGE = os.environ.get("SAHULAT_VOICE_ALT_LANGUAGE", "ps")
SUMMARY_KEY = "sindhi" if TARGET_LANGUAGE == "sd" else "pashto"
PROTOCOL_ID = os.environ.get("SAHULAT_VOICE_ALT_PROTOCOL", "EVAL-VOICE-ALT-V1")
PREREG_VERSION = os.environ.get("SAHULAT_VOICE_ALT_PREREG_VERSION", "eval-voice-alt-v1")
RESULT_VERSION = os.environ.get("SAHULAT_VOICE_ALT_RESULT_VERSION", "eval-voice-alt-result-v1")
VALIDATION_VERSION = os.environ.get(
    "SAHULAT_VOICE_ALT_VALIDATION_VERSION", "eval-voice-alt-validation-v1"
)
REGISTRY = os.environ.get("SAHULAT_VOICE_ALT_REGISTRY", "configs/gates/eval_voice_alt_v1.json")
RESULT_REGISTRY = os.environ.get(
    "SAHULAT_VOICE_ALT_RESULT_REGISTRY", "configs/gates/eval_voice_alt_v1_result.json"
)
PROTOCOL_DOC = os.environ.get("SAHULAT_VOICE_ALT_PROTOCOL_DOC", "docs/EVAL-VOICE-ALT-V1.md")
RUN_SCRIPT = os.environ.get("SAHULAT_VOICE_ALT_RUN_SCRIPT", "scripts/run_voice_alt_v1.py")
HISTORICAL = {
    "artifacts/eval_voice_run_v1/whisper.json": (
        "ec6a5ec25f684c7afc9a0313e5da0813da94b1b8d92543f9dc57c09820cb86df"
    ),
    "artifacts/eval_voice_run_v1/mms.json": (
        "f617a2c63d64962e914b82f149afb8b3a4c9d3bc3eca3ae44605ac06d7b1c6db"
    ),
    "artifacts/eval_voice_run_v1/manifest.json": (
        "1748308d5dacda3efd3b6bb2492605984ed13752803743e67fef5ee7fda5f056"
    ),
}


def prerequisites(root: Path) -> tuple[dict[str, Any], list[EvaluationSample]]:
    descriptor, inputs = verified_input(root)
    for path, expected in HISTORICAL.items():
        if file_sha256(root / path) != expected:
            raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    samples = [s for s in inputs.samples if s.language.value == TARGET_LANGUAGE]
    if len(samples) != 50:
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    return descriptor, samples


def fingerprints(root: Path) -> dict[str, str]:
    paths = [
        CONFIG,
        PROTOCOL_DOC,
        RUN_SCRIPT,
        "scripts/acquire_voice_alt_models_v1.py",
        "scripts/acquire_voice_models_v1.py",
        "scripts/sindhi_holdout_v1.py",
        "src/sahulat_voice/alternatives/metadata.py",
        "src/sahulat_voice/alternatives/adapters.py",
        "src/sahulat_voice/alternatives/runner.py",
        "src/sahulat_voice/alternatives/holdout.py",
        "src/sahulat_voice/runs/execution.py",
        "src/sahulat_voice/runs/scoring.py",
        "src/sahulat_voice/adapters.py",
        "src/sahulat_voice/service.py",
        "src/sahulat_voice/contracts.py",
        "src/sahulat_voice/audio.py",
        "src/sahulat_voice/transcript.py",
    ]
    return {path: file_sha256(root / path) for path in paths}


def preregistration(root: Path) -> dict[str, Any]:
    descriptor, samples = prerequisites(root)
    return {
        "protocol_id": PROTOCOL_ID,
        "version": PREREG_VERSION,
        "dataset": descriptor,
        "candidates": candidates(root),
        "historical_files_sha256": HISTORICAL,
        "historical_inventory_sha256": {
            path.relative_to(root).as_posix(): file_sha256(path)
            for path in sorted((root / "artifacts/eval_voice_run_v1").rglob("*"))
            if path.is_file()
        },
        "implementation_files_sha256": fingerprints(root),
        "scored_sample_ids": [s.sample_id for s in samples],
        "unscored_warmup_sample_id": first_selected(samples).sample_id,
        "scored_calls_per_sample": 1,
        "inference_retries": 0,
        "sindhi_fleurs_inference": "NOT_RUN",
        "sindhi_independent_holdout": "PENDING",
    }


def register(root: Path) -> None:
    if (root / OUTPUT / "execution.started.json").exists():
        raise VoiceError(ErrorCode.INVALID_CONFIG)
    record = preregistration(root)
    put_json(root / OUTPUT / "preregistration.json", record)
    put_json(
        root / REGISTRY,
        {
            "protocol_id": PROTOCOL_ID,
            "preregistration_sha256": record_checksum(record),
        },
    )


def verify_registration(root: Path) -> dict[str, Any]:
    current = preregistration(root)
    if read_canonical_json(
        root / OUTPUT / "preregistration.json"
    ) != current or read_canonical_json(root / REGISTRY) != {
        "protocol_id": PROTOCOL_ID,
        "preregistration_sha256": record_checksum(current),
    }:
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    return current


def summarize_target(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records or any(r["language"] != TARGET_LANGUAGE for r in records):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    totals = {
        key: sum(r["scoring"][key] for r in records)
        for key in ("reference_words", "reference_characters", "word_errors", "character_errors")
    }
    timed = [r for r in records if r["timing"] is not None]
    return {
        **totals,
        "sample_count": len(records),
        "successful_samples": sum(r["status"] == "SUCCESS" for r in records),
        "failed_samples": sum(r["status"] == "FAILED" for r in records),
        "wer": totals["word_errors"] / totals["reference_words"],
        "cer": totals["character_errors"] / totals["reference_characters"],
        "aggregation": f"{SUMMARY_KEY.title()}-only-micro;no-overall-macro",
        "timed_calls": len(timed),
        "latency_ms": distribution([r["timing"]["stt_ms"] for r in timed]),
        "real_time_factor": distribution(
            [r["timing"]["stt_ms"] / (1000 * r["audio_duration_seconds"]) for r in timed]
        ),
    }


summarize_pashto = summarize_target


def execute(root: Path) -> dict[str, Any]:
    registration = verify_registration(root)
    assets = verified_assets(root, KEY)
    output = root / OUTPUT
    if not (output / "execution.started.json").exists() and (
        (output / f"{KEY}.json").exists() or any((output / KEY / "samples").glob("*.json"))
    ):
        raise VoiceError(ErrorCode.INVALID_CONFIG)
    # The marker is exclusive and permanent, including crashes: no favorable resume/retry.
    marker = output / "execution.started.json"
    from ..transcript import canonical_bytes

    with marker.open("xb") as stream:
        stream.write(canonical_bytes({"preregistration_sha256": record_checksum(registration)}))
    _, samples = prerequisites(root)
    candidate = candidates(root)[KEY]
    adapter = SpecialistWhisperAdapter(root, KEY)
    service = TranscriptionService(CaptureAdapter(adapter))
    start = perf_counter()
    failure = None
    try:
        adapter._load()
    except VoiceError as error:
        failure = error.code.value
    load = {"duration_ms": (perf_counter() - start) * 1000, "failure_code": failure}
    bundle = root / ARTIFACT_PATH
    warmup = None if failure else sample_call(service, first_selected(samples), bundle)
    records = []
    for sample in samples:
        if failure:
            record = {
                "schema_version": "voice-scored-sample-v1",
                "sample_id": sample.sample_id,
                "language": TARGET_LANGUAGE,
                "audio_sha256": sample.audio_sha256,
                "audio_duration_seconds": read_evaluation_audio(bundle, sample).duration_seconds,
                "model": model_identity_key(adapter.spec),
                "status": "FAILED",
                "failure_code": failure,
                "failure_stage": "base_load",
                "raw_decoder_output": None,
                "raw_decoder_codepoints_if_invalid_utf8": None,
                "transcript": None,
                "scoring": score(sample.reference_text, ""),
                "timing": None,
            }
        else:
            record = sample_call(service, sample, bundle)
        # Independence flags accompany every emitted sample, not just the report.
        record.update(
            {key: candidate[key] for key in ("evaluation_independence", "reason", "evidence_class")}
        )
        put_json(output / KEY / "samples" / f"{sample.sample_id}.json", record)
        records.append(record)
        print(f"{KEY}:{TARGET_LANGUAGE}:recorded={len(records)}/50", flush=True)
    result = {
        "version": RESULT_VERSION,
        "protocol_id": PROTOCOL_ID,
        "preregistration_sha256": record_checksum(registration),
        "candidate": candidate,
        "evaluation_independence": candidate["evaluation_independence"],
        "reason": candidate["reason"],
        "dataset": registration["dataset"],
        "normalization_version": NORMALIZATION_VERSION,
        "acquired_assets": assets,
        "environment": environment(),
        "records": records,
        "base_load": load,
        "unscored_warmup": warmup,
        "inference_retries": 0,
        "semantic_results_sha256": record_checksum(
            [{k: v for k, v in r.items() if k != "timing"} for r in records]
        ),
        "summary": summarize_target(records),
    }
    verify_registration(root)
    put_json(output / f"{KEY}.json", result)
    return result


def verify_sample(
    root: Path, sample: EvaluationSample, record: dict[str, Any], *, tagged: bool
) -> None:
    candidate = candidates(root)[KEY]
    model = spec(candidate)
    expected_keys = {
        "schema_version",
        "sample_id",
        "language",
        "audio_sha256",
        "audio_duration_seconds",
        "model",
        "status",
        "failure_code",
        "failure_stage",
        "raw_decoder_output",
        "raw_decoder_codepoints_if_invalid_utf8",
        "transcript",
        "scoring",
        "timing",
    }
    if tagged:
        expected_keys |= {"evaluation_independence", "reason", "evidence_class"}
    if (
        set(record) != expected_keys
        or record["schema_version"] != "voice-scored-sample-v1"
        or record["sample_id"] != sample.sample_id
        or record["audio_sha256"] != sample.audio_sha256
        or record["language"] != TARGET_LANGUAGE
        or record["model"] != model_identity_key(model)
        or record["audio_duration_seconds"]
        != read_evaluation_audio(root / ARTIFACT_PATH, sample).duration_seconds
        or (
            tagged
            and any(
                record[key] != candidate[key]
                for key in ("evaluation_independence", "reason", "evidence_class")
            )
        )
    ):
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    transcript = record["transcript"]
    if record["status"] == "SUCCESS":
        expected = build_transcript(
            sample.audio_sha256, sample.language, model, record["raw_decoder_output"]
        ).record()
        if (
            transcript != expected
            or record["failure_code"] is not None
            or record["failure_stage"] is not None
            or record["timing"] is None
            or record["raw_decoder_codepoints_if_invalid_utf8"] is not None
        ):
            raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    elif (
        record["status"] != "FAILED"
        or transcript is not None
        or record["failure_code"] not in {c.value for c in ErrorCode}
        or record["failure_stage"] not in ("base_load", "scored_call")
        or (record["failure_stage"] == "scored_call") != (record["timing"] is not None)
    ):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    if record["scoring"] != score(sample.reference_text, transcript["text"] if transcript else ""):
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    if record["timing"] is not None:
        if set(record["timing"]) != {
            "audio_validation_ms",
            "stt_ms",
            "total_ms",
            "adapter_base_model_load_ms_lifetime",
        }:
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        for value in record["timing"].values():
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (float, int))
                or not math.isfinite(value)
                or value < 0
            ):
                raise VoiceError(ErrorCode.INVALID_MANIFEST)
        if record["timing"]["stt_ms"] is None:
            raise VoiceError(ErrorCode.INVALID_MANIFEST)


def verify(root: Path) -> dict[str, Any]:
    registration = verify_registration(root)
    candidate = candidates(root)[KEY]
    path = root / OUTPUT / f"{KEY}.json"
    result = read_canonical_json(path)
    if read_canonical_json(root / OUTPUT / "execution.started.json") != {
        "preregistration_sha256": record_checksum(registration)
    }:
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    _, samples = prerequisites(root)
    if (
        result["candidate"] != candidate
        or result["dataset"] != registration["dataset"]
        or result["version"] != RESULT_VERSION
        or result["protocol_id"] != PROTOCOL_ID
        or result["preregistration_sha256"] != record_checksum(registration)
        or result["evaluation_independence"] is not False
        or result["reason"] != candidate["reason"]
        or result["normalization_version"] != NORMALIZATION_VERSION
        or result["inference_retries"] != 0
        or result["environment"]["device"] != "cpu"
        or result["environment"]["dtype"] != "float32"
        or result["environment"]["torch_threads"] != 8
        or result["environment"]["torch_interop_threads"] != 8
        or result["acquired_assets"] != verified_assets(root, KEY)
        or [r["sample_id"] for r in result["records"]] != [s.sample_id for s in samples]
    ):
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    for sample, record in zip(samples, result["records"], strict=True):
        verify_sample(root, sample, record, tagged=True)
        checkpoint = root / OUTPUT / KEY / "samples" / f"{sample.sample_id}.json"
        if read_canonical_json(checkpoint) != record:
            raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    if {p.stem for p in (root / OUTPUT / KEY / "samples").glob("*.json")} != {
        s.sample_id for s in samples
    }:
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    semantic = [{k: v for k, v in r.items() if k != "timing"} for r in result["records"]]
    if result["summary"] != summarize_target(result["records"]) or result[
        "semantic_results_sha256"
    ] != record_checksum(semantic):
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    warmup = result["unscored_warmup"]
    if (
        result["base_load"]["failure_code"] is None
        and (warmup is None or warmup["sample_id"] != first_selected(samples).sample_id)
    ) or (result["base_load"]["failure_code"] is not None and warmup is not None):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    if warmup is not None:
        verify_sample(root, first_selected(samples), warmup, tagged=False)
    for key, record in candidates(root).items():
        validate_official(
            record,
            read_canonical_json(root / metadata.ASSET_OUTPUT / f"{key}-official-metadata.json"),
            (root / metadata.ASSET_OUTPUT / f"{key}-README.md").read_bytes(),
        )
    evidence = {
        "version": VALIDATION_VERSION,
        "protocol_id": PROTOCOL_ID,
        "result_sha256": file_sha256(path),
        "semantic_results_sha256": result["semantic_results_sha256"],
        "dataset_manifest_sha256": registration["dataset"]["manifest_sha256"],
        "historical_files_unchanged": True,
        SUMMARY_KEY: result["summary"],
        "evaluation_independence": False,
        "reason": candidate["reason"],
        "sindhi_compatibility_inference": "NOT_RUN",
        "sindhi_holdout": "PENDING",
        "production_selection": "NOT_AUTHORIZED",
    }
    return evidence
