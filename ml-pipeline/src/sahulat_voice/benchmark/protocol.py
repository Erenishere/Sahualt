import sys
import unicodedata
from pathlib import Path

import numpy as np

from ..contracts import MODEL_SPECS
from ..errors import ErrorCode, VoiceError
from ..transcript import normalize_transcript
from .io import file_sha256, put_json, read_canonical_json, read_json, record_checksum
from .source import load_source_lock

PROTOCOL_ID = "EVAL-VOICE-V1"
DATASET_ID = "FLEURS-VOICE-V1"
REGISTRY_PATH = "configs/gates/eval_voice_v1_protocol.json"
CORPUS_PATH = "configs/corpora/fleurs_voice_v1.json"
ARTIFACT_PATH = "artifacts/voice_evaluation_v1"
LANGUAGE_CONFIGS = {"en": "en_us", "ur": "ur_pk", "sd": "sd_in", "ps": "ps_af"}


def scoring_text(raw: str) -> str:
    normalized = normalize_transcript(raw).casefold()
    return " ".join(
        "".join(
            " " if unicodedata.category(char).startswith("P") else char for char in normalized
        ).split()
    )


def runtime_identity() -> dict[str, str]:
    if (
        sys.version_info[:2] != (3, 12)
        or unicodedata.unidata_version != "15.0.0"
        or np.__version__ != "2.2.6"
    ):
        raise VoiceError(ErrorCode.INVALID_CONFIG)
    return {"python": "3.12", "unicode": unicodedata.unidata_version, "numpy": np.__version__}


def protocol_inputs(root: Path) -> tuple[dict, dict]:
    protocol = read_json(root / "configs/eval_voice_v1.json")
    source = load_source_lock(root / "configs/fleurs_sources_v1.json")
    models = {
        name: {"repository": spec.repository, "revision": spec.revision}
        for name, spec in MODEL_SPECS.items()
    }
    if (
        not isinstance(protocol, dict)
        or set(protocol)
        != {
            "protocol_version",
            "protocol_status",
            "dataset_id",
            "source_lock",
            "split",
            "samples_per_language",
            "sample_count",
            "language_configs",
            "selection",
            "reference",
            "audio_preparation",
            "scoring",
            "models",
            "experiment",
        }
        or any(
            not isinstance(protocol.get(section), dict)
            for section in ("selection", "reference", "audio_preparation", "scoring", "experiment")
        )
        or protocol.get("protocol_version") != PROTOCOL_ID
        or protocol.get("dataset_id") != DATASET_ID
        or protocol.get("split") != "test"
        or type(protocol.get("samples_per_language")) is not int
        or protocol["samples_per_language"] != 50
        or protocol.get("sample_count") != 200
        or protocol.get("language_configs") != LANGUAGE_CONFIGS
        or protocol.get("source_lock") != "configs/fleurs_sources_v1.json"
        or protocol.get("models") != models
        or protocol.get("protocol_status") != "PREREGISTERED"
        or protocol.get("selection", {}).get("seed") != 20260912
        or protocol.get("selection", {}).get("version") != "fleurs-selection-v1"
        or protocol.get("reference", {}).get("primary_source_field") != "raw_transcription"
        or protocol.get("audio_preparation", {}).get("version") != "fleurs-pcm16-v1"
        or protocol.get("scoring", {}).get("version") != "voice-asr-scoring-v1"
        or protocol["selection"].get("unique_sentence_ids_per_language") is not True
        or protocol["selection"].get("selected_audio_failure") != "fail-no-replacement"
        or protocol["reference"].get("preserve_exact_published_text") is not True
        or any(
            protocol["audio_preparation"].get(key) is not False
            for key in ("resample", "denoise", "trim")
        )
        or protocol["experiment"].get("no_model_execution_before_subset_freeze") is not True
        or protocol["experiment"].get("no_training_or_tuning") is not True
    ):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    return protocol, source


def _registry_record(root: Path) -> dict[str, object]:
    protocol, source = protocol_inputs(root)
    package = root / "src/sahulat_voice"
    paths = [
        root / "configs/eval_voice_v1.json",
        root / "configs/fleurs_sources_v1.json",
        root / "docs/EVAL-VOICE-V1.md",
    ]
    paths += list((package / "benchmark").glob("*.py"))
    paths += [
        package / filename
        for filename in ("audio.py", "contracts.py", "errors.py", "evaluation.py", "transcript.py")
    ]
    files = {path.relative_to(root).as_posix(): file_sha256(path) for path in sorted(paths)}
    record = {
        "registry_version": "eval-voice-protocol-freeze-v1",
        "protocol_id": PROTOCOL_ID,
        "protocol_sha256": record_checksum(protocol),
        "dataset_id": DATASET_ID,
        "dataset_revision": source["revision"],
        "source_lock_sha256": record_checksum(source),
        "status": "FROZEN_PROTOCOL_ONLY",
        "human_dataset_status": "NOT_YET_FROZEN",
        "model_results": "NOT_RUN",
        "files": files,
    }
    return {**record, "registry_checksum": record_checksum(record)}


def preregister(root: Path) -> dict[str, object]:
    # No acquisition/model call is made here. Existing different preregistration is immutable.
    record = _registry_record(root)
    put_json(root / REGISTRY_PATH, record)
    return verify_protocol(root)


def verify_protocol(root: Path) -> dict[str, object]:
    expected = _registry_record(root)
    actual = read_canonical_json(root / REGISTRY_PATH)
    if actual != expected:
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    return expected
