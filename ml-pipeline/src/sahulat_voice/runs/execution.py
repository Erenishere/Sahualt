import hashlib
import importlib.metadata
import math
import os
import platform
import re
from pathlib import Path
from time import perf_counter
from typing import Any

from ..adapters import HuggingFaceAdapter, STTAdapter, create_adapter
from ..audio import MAX_AUDIO_BYTES, ValidatedAudio
from ..benchmark.dataset import verify_frozen
from ..benchmark.io import file_sha256, put_json, read_canonical_json, record_checksum
from ..benchmark.protocol import ARTIFACT_PATH, LANGUAGE_CONFIGS, PROTOCOL_ID, runtime_identity
from ..contracts import (
    MMS_LANGUAGES,
    MODEL_SPECS,
    NORMALIZATION_VERSION,
    Language,
    ModelSpec,
    RuntimeSettings,
)
from ..errors import ErrorCode, VoiceError
from ..evaluation import (
    EvaluationInput,
    EvaluationSample,
    load_evaluation_input,
    read_evaluation_audio,
)
from ..service import TranscriptionService
from .scoring import score, summarize

EXPECTED_MANIFEST = "e2efd78d0af8fe8ecc2c6483ab7db0ff9dba6763fd148be58bbc6c4fd05499e4"
RUN_VERSION = "eval-voice-run-v1"


def first_selected(samples: list[EvaluationSample]) -> EvaluationSample:
    def key(sample: EvaluationSample) -> tuple[str, str]:
        filename = Path(sample.audio_path).name
        value = f"EVAL-VOICE-V1|20260912|{LANGUAGE_CONFIGS[sample.language.value]}|{filename}"
        return hashlib.sha256(value.encode("utf-8")).hexdigest(), filename

    return min(samples, key=key)


def acquired_assets(root: Path, name: str, check_cache: bool) -> dict[str, Any]:
    metadata = read_canonical_json(root / "artifacts/eval_voice_run_v1/model_acquisition.json")
    if metadata.get("version") != "voice-model-acquisition-v1":
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    candidates = [record for record in metadata["models"] if record["model"] == name]
    if len(candidates) != 1:
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    identity = candidates[0]
    spec = MODEL_SPECS[name]
    if identity["repository"] != spec.repository or identity["revision"] != spec.revision:
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    snapshot = (
        root
        / ".cache/voice/huggingface/hub"
        / ("models--" + spec.repository.replace("/", "--"))
        / "snapshots"
        / spec.revision
    )
    names = [asset["file"] for asset in identity["files"]]
    required = {
        "model.safetensors",
        "config.json",
        "preprocessor_config.json",
        "vocab.json",
        "tokenizer_config.json",
    }
    if name == "mms":
        required |= {f"adapter.{code}.safetensors" for code in MMS_LANGUAGES.values()}
    if len(names) != len(set(names)) or not required <= set(names):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    for asset in identity["files"]:
        if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,128}", asset["file"]):
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        path = snapshot / asset["file"]
        if not path.resolve().is_relative_to(root.resolve()):
            raise VoiceError(ErrorCode.INVALID_CONFIG)
        if check_cache and (
            path.stat().st_size != asset["size"] or file_sha256(path) != asset["sha256"]
        ):
            raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    return identity


def verified_input(root: Path) -> tuple[dict[str, Any], EvaluationInput]:
    descriptor = verify_frozen(root)
    if descriptor["manifest_sha256"] != EXPECTED_MANIFEST:
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    inputs = load_evaluation_input(
        root / ARTIFACT_PATH / "evaluation-input.json", root / ARTIFACT_PATH
    )
    if len(inputs.samples) != descriptor["sample_count"]:
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    return descriptor, inputs


def environment() -> dict[str, Any]:
    import torch

    packages = ("torch", "transformers", "huggingface_hub", "safetensors", "numpy", "tokenizers")
    return {
        "canonical_runtime": runtime_identity(),
        "python": platform.python_version(),
        "system": platform.system(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "logical_cpu_count": os.cpu_count(),
        "device": "cpu",
        "dtype": "float32",
        "torch_threads": torch.get_num_threads(),
        "torch_interop_threads": torch.get_num_interop_threads(),
        "dependencies": {package: importlib.metadata.version(package) for package in packages},
    }


def implementation(root: Path) -> dict[str, str]:
    paths = [
        "src/sahulat_voice/adapters.py",
        "src/sahulat_voice/service.py",
        "src/sahulat_voice/runs/execution.py",
        "src/sahulat_voice/runs/scoring.py",
        "scripts/run_voice_evaluation.py",
    ]
    return {path: file_sha256(root / path) for path in paths}


class CaptureAdapter(STTAdapter):
    """Retain decoder output even when the unchanged service rejects an empty transcript."""

    def __init__(self, delegate: STTAdapter) -> None:
        self.delegate = delegate
        self.spec = delegate.spec
        self.raw: str | None = None
        self.load_time_ms = delegate.load_time_ms
        self.stt_ms = 0.0

    def transcribe(self, audio: ValidatedAudio, language: Language) -> str:
        self.raw = None
        started = perf_counter()
        try:
            self.raw = self.delegate.transcribe(audio, language)
            return self.raw
        finally:
            self.stt_ms = (perf_counter() - started) * 1000
            self.load_time_ms = self.delegate.load_time_ms


def model_identity(name: str) -> dict[str, Any]:
    spec = MODEL_SPECS[name]
    return {
        "name": spec.name,
        "repository": spec.repository,
        "revision": spec.revision,
        "license": spec.license,
        "decoding": (
            {
                "task": "transcribe",
                "do_sample": False,
                "num_beams": 1,
                "max_new_tokens": 256,
                "return_timestamps": False,
            }
            if name == "whisper"
            else {"decoder": "finite-logit-CTC-argmax"}
        ),
        "language_paths": {
            language.value: language.value if name == "whisper" else MMS_LANGUAGES[language]
            for language in Language
        },
    }


def sample_call(
    service: TranscriptionService, sample: EvaluationSample, bundle: Path
) -> dict[str, Any]:
    audio = read_evaluation_audio(bundle, sample)
    with (bundle / sample.audio_path).open("rb") as stream:
        payload = stream.read(MAX_AUDIO_BYTES + 1)
    if hashlib.sha256(payload).hexdigest() != sample.audio_sha256:
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    capture = service.adapter
    if not isinstance(capture, CaptureAdapter):
        raise VoiceError(ErrorCode.INVALID_CONFIG)
    transcript: dict[str, Any] | None
    timing: dict[str, float | None]
    hypothesis = ""
    try:
        result = service.transcribe(payload, sample.language.value)
        transcript, status, failure = result.transcript.record(), "SUCCESS", None
        hypothesis = result.transcript.text
        timing = {
            "audio_validation_ms": result.audio_validation_ms,
            "stt_ms": result.stt_ms,
            "total_ms": result.total_ms,
            "adapter_base_model_load_ms_lifetime": result.model_load_ms,
        }
    except VoiceError as error:
        transcript, status, failure = None, "FAILED", error.code.value
        # Already-validated payload; failed model/decoder calls remain in the timed population.
        timing = {
            "stt_ms": capture.stt_ms,
            "audio_validation_ms": None,
            "total_ms": None,
            "adapter_base_model_load_ms_lifetime": capture.load_time_ms,
        }
    raw = capture.raw
    # Invalid surrogate output cannot be encoded as UTF-8; retain exact codepoints as evidence.
    codepoints = None
    if raw is not None:
        try:
            raw.encode("utf-8")
        except UnicodeError:
            codepoints, raw = [ord(char) for char in raw], None
    return {
        "schema_version": "voice-scored-sample-v1",
        "sample_id": sample.sample_id,
        "language": sample.language.value,
        "audio_sha256": sample.audio_sha256,
        "audio_duration_seconds": audio.duration_seconds,
        "model": model_identity_key(capture.spec),
        "status": status,
        "failure_code": failure,
        "failure_stage": "scored_call" if failure else None,
        "raw_decoder_output": raw,
        "raw_decoder_codepoints_if_invalid_utf8": codepoints,
        "transcript": transcript,
        "scoring": score(sample.reference_text, hypothesis),
        "timing": timing,
    }


def model_identity_key(spec: ModelSpec) -> dict[str, str]:
    return {"name": spec.name, "repository": spec.repository, "revision": spec.revision}


def unavailable_sample(
    sample: EvaluationSample, bundle: Path, name: str, code: str, stage: str
) -> dict[str, Any]:
    spec = MODEL_SPECS[name]
    return {
        "schema_version": "voice-scored-sample-v1",
        "sample_id": sample.sample_id,
        "language": sample.language.value,
        "audio_sha256": sample.audio_sha256,
        "audio_duration_seconds": read_evaluation_audio(bundle, sample).duration_seconds,
        "model": model_identity_key(spec),
        "status": "FAILED",
        "failure_code": code,
        "failure_stage": stage,
        "raw_decoder_output": None,
        "raw_decoder_codepoints_if_invalid_utf8": None,
        "transcript": None,
        "scoring": score(sample.reference_text, ""),
        "timing": None,
    }


def execute_model(root: Path, output: Path, name: str) -> dict[str, Any]:
    descriptor, inputs = verified_input(root)
    if name not in MODEL_SPECS or output.exists():
        raise VoiceError(ErrorCode.INVALID_CONFIG)
    asset_identity = acquired_assets(root, name, check_cache=True)
    code_identity = implementation(root)
    adapter = create_adapter(name, RuntimeSettings("cpu", local_files_only=True))
    if not isinstance(adapter, HuggingFaceAdapter):
        raise VoiceError(ErrorCode.INVALID_CONFIG)
    capture = CaptureAdapter(adapter)
    service = TranscriptionService(capture)
    bundle = root / ARTIFACT_PATH
    records: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    start = perf_counter()
    base_failure = None
    try:
        adapter._load()
    except VoiceError as error:
        base_failure = error.code.value
    observations.append(
        {
            "stage": "fresh_process_base_load",
            "duration_ms": (perf_counter() - start) * 1000,
            "failure_code": base_failure,
        }
    )
    for language in Language:
        samples = [sample for sample in inputs.samples if sample.language == language]
        load_failure = base_failure
        if not load_failure:
            start = perf_counter()
            try:
                adapter._prepare_language(language)
            except VoiceError as error:
                load_failure = error.code.value
            observations.append(
                {
                    "stage": "language_adapter_load",
                    "language": language.value,
                    "duration_ms": (perf_counter() - start) * 1000,
                    "failure_code": load_failure,
                }
            )
        if load_failure:
            records.extend(
                unavailable_sample(
                    sample,
                    bundle,
                    name,
                    load_failure,
                    "base_load" if base_failure else "language_adapter_load",
                )
                for sample in samples
            )
        else:
            warmup = sample_call(service, first_selected(samples), bundle)
            observations.append(
                {"stage": "unscored_warmup", "language": language.value, "sample": warmup}
            )
            for sample in samples:
                record = sample_call(service, sample, bundle)
                records.append(record)
                # Crash checkpoints are evidence only, never read to retry/replace a scored call.
                put_json(output.parent / name / "samples" / f"{sample.sample_id}.json", record)
        print(f"{name}:{language.value}:recorded={len(samples)}", flush=True)
    records.sort(key=lambda record: record["sample_id"])
    semantic_records = [
        {key: value for key, value in record.items() if key != "timing"} for record in records
    ]
    result = {
        "run_version": RUN_VERSION,
        "protocol_id": PROTOCOL_ID,
        "dataset": descriptor,
        "normalization_version": NORMALIZATION_VERSION,
        "model": model_identity(name),
        "acquired_model_assets": asset_identity,
        "environment": environment(),
        "implementation_files_sha256": code_identity,
        "records": records,
        "load_and_warmup_observations": observations,
        "semantic_results_sha256": record_checksum(semantic_records),
        "summary": summarize(records),
        "status": "LOAD_FAILED" if base_failure else "EXECUTED",
        "retries": 0,
    }
    # Detect source/protocol drift during a long run before declaring completed evidence.
    verified_input(root)
    if implementation(root) != code_identity:
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    put_json(output, result)
    return result


def verify_model(root: Path, output: Path, name: str) -> dict[str, Any]:
    descriptor, inputs = verified_input(root)
    result = read_canonical_json(output)
    if (
        result["dataset"] != descriptor
        or result["model"] != model_identity(name)
        or result["acquired_model_assets"] != acquired_assets(root, name, check_cache=False)
        or result["run_version"] != RUN_VERSION
        or result["retries"] != 0
        or result["normalization_version"] != NORMALIZATION_VERSION
        or result["implementation_files_sha256"] != implementation(root)
        or result["protocol_id"] != PROTOCOL_ID
        or result["environment"]["device"] != "cpu"
        or result["environment"]["dtype"] != "float32"
    ):
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    records = result["records"]
    if [record["sample_id"] for record in records] != [
        sample.sample_id for sample in inputs.samples
    ]:
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    for sample, record in zip(inputs.samples, records, strict=True):
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
        spec = MODEL_SPECS[name]
        if (
            set(record) != expected_keys
            or record["schema_version"] != "voice-scored-sample-v1"
            or record["model"] != model_identity_key(spec)
        ):
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        if (
            record["language"] != sample.language.value
            or record["audio_sha256"] != sample.audio_sha256
        ):
            raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
        transcript = record["transcript"]
        if record["status"] == "SUCCESS":
            from ..transcript import build_transcript

            expected = build_transcript(
                sample.audio_sha256,
                sample.language,
                MODEL_SPECS[name],
                record["raw_decoder_output"],
            ).record()
            if (
                transcript != expected
                or record["failure_code"] is not None
                or record["failure_stage"] is not None
                or record["timing"] is None
            ):
                raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
        elif (
            record["status"] != "FAILED"
            or transcript is not None
            or record["failure_code"] not in {code.value for code in ErrorCode}
        ):
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        if record["status"] == "FAILED" and (
            record["failure_stage"] not in ("base_load", "language_adapter_load", "scored_call")
            or (record["failure_stage"] == "scored_call") != (record["timing"] is not None)
        ):
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        if record["scoring"] != score(
            sample.reference_text, transcript["text"] if transcript else ""
        ):
            raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
        if record["timing"] is not None:
            value = record["timing"]["stt_ms"]
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise VoiceError(ErrorCode.INVALID_MANIFEST)
    semantic = [
        {key: value for key, value in record.items() if key != "timing"} for record in records
    ]
    if result["summary"] != summarize(records) or result[
        "semantic_results_sha256"
    ] != record_checksum(semantic):
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    observations = result["load_and_warmup_observations"]
    if not observations or observations[0]["stage"] != "fresh_process_base_load":
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    for language in Language:
        scored = [r for r in records if r["language"] == language.value and r["timing"] is not None]
        warmups = [
            observation
            for observation in observations
            if observation["stage"] == "unscored_warmup"
            and observation["language"] == language.value
        ]
        if scored:
            expected_id = first_selected(
                [s for s in inputs.samples if s.language == language]
            ).sample_id
            if len(warmups) != 1 or warmups[0]["sample"]["sample_id"] != expected_id:
                raise VoiceError(ErrorCode.INVALID_MANIFEST)
        elif warmups:
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
    return {
        "model": name,
        "status": "VERIFIED",
        "result_sha256": file_sha256(output),
        "semantic_results_sha256": result["semantic_results_sha256"],
        "summary": result["summary"],
    }
