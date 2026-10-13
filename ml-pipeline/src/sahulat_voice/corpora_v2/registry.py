import re
from pathlib import Path
from typing import Any

from ..benchmark.io import file_sha256, put_json, read_canonical_json, read_json, record_checksum
from ..errors import ErrorCode, VoiceError

PROTOCOL_ID = "EVAL-VOICE-CORPORA-V2"
CONFIG_PATH = "configs/voice_corpora_v2.json"
PROTOCOL_GATE_PATH = "configs/gates/eval_voice_corpora_v2_protocol.json"
AUDIT_GATE_PATH = "configs/gates/eval_voice_corpora_v2_audit.json"
AUDIT_JSON_PATH = "reports/eval_voice_corpora_v2_source_audit.json"
AUDIT_MARKDOWN_PATH = "reports/eval_voice_corpora_v2_source_audit.md"

SOURCE_IDS = {
    "common_voice_27_sindhi",
    "pashto_audio_visual",
    "sindhi_holdout_v1",
    "south_asian_english",
    "urduspeech",
}
URDUSPEECH_SUBSETS = {"code_switched", "pakistani_english", "standard_urdu"}


def _is_sha(value: object, length: int) -> bool:
    return isinstance(value, str) and re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is not None


def load_registry(root: Path) -> dict[str, Any]:
    document = read_json(root / CONFIG_PATH)
    if (
        not isinstance(document, dict)
        or set(document) != {"schema_version", "protocol", "sources"}
        or document.get("schema_version") != "eval-voice-corpora-v2-registry-v1"
        or not isinstance(document.get("protocol"), dict)
        or not isinstance(document.get("sources"), dict)
        or set(document["sources"]) != SOURCE_IDS
    ):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)

    protocol = document["protocol"]
    if (
        set(protocol)
        != {
            "id",
            "status",
            "selection_seed",
            "frozen_v1_policy",
            "no_audio_download_before_source_gate",
            "no_model_execution_before_dataset_freeze",
            "no_training_or_tuning",
        }
        or protocol.get("id") != PROTOCOL_ID
        or protocol.get("status") != "PREREGISTERED_METADATA_ONLY"
        or protocol.get("selection_seed") != 20261012
        or protocol.get("frozen_v1_policy") != "VERIFY_ONLY_DO_NOT_MODIFY"
        or protocol.get("no_audio_download_before_source_gate") is not True
        or protocol.get("no_model_execution_before_dataset_freeze") is not True
        or protocol.get("no_training_or_tuning") is not True
    ):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)

    sources = document["sources"]
    urdu = sources["urduspeech"]
    expected = urdu.get("expected_inventory")
    subsets = urdu.get("subsets")
    if (
        urdu.get("source_type") != "huggingface_dataset"
        or urdu.get("repository") != "ASLP-lab/UrduSpeech"
        or not _is_sha(urdu.get("revision"), 40)
        or urdu.get("benchmark_root") != "benchmark"
        or urdu.get("declared_license") != "cc-by-4.0"
        or urdu.get("structured_hub_license") != "MISSING"
        or urdu.get("rights_review") != "REQUIRED"
        or urdu.get("evaluation_independence") != "NOT_VERIFIED"
        or urdu.get("acquisition_status") != "BLOCKED"
        or not isinstance(expected, dict)
        or set(expected)
        != {
            "file_count",
            "byte_count",
            "audio_file_count",
            "metadata_file_count",
            "metadata_byte_count",
            "inventory_sha256",
        }
        or expected.get("file_count") != 4288
        or expected.get("byte_count") != 3561652930
        or expected.get("audio_file_count") != 4170
        or expected.get("metadata_file_count") != 118
        or expected.get("metadata_byte_count") != 6211778
        or not _is_sha(expected.get("inventory_sha256"), 64)
        or not isinstance(subsets, dict)
        or set(subsets) != URDUSPEECH_SUBSETS
    ):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)

    subset_contract = {
        "standard_urdu": ("benchmark/US-benchmark-Std", "ur", 200, True, 2221, 1397580773),
        "code_switched": ("benchmark/US-benchmark-CS", "ur-en", 200, True, 1901, 2098847758),
        "pakistani_english": (
            "benchmark/US-benchmark-EngPk",
            "en-pk",
            200,
            False,
            166,
            65224399,
        ),
    }
    for key, (path, language, target, required, files, size) in subset_contract.items():
        record = subsets[key]
        if (
            not isinstance(record, dict)
            or set(record)
            != {
                "path",
                "language",
                "sample_target",
                "required_for_gate",
                "use_all_if_fewer",
                "expected_file_count",
                "expected_byte_count",
            }
            or record.get("path") != path
            or record.get("language") != language
            or record.get("sample_target") != target
            or record.get("required_for_gate") is not required
            or record.get("use_all_if_fewer") is not True
            or record.get("expected_file_count") != files
            or record.get("expected_byte_count") != size
        ):
            raise VoiceError(ErrorCode.INVALID_MANIFEST)

    sindhi = sources["common_voice_27_sindhi"]
    if (
        sindhi.get("source_type") != "mozilla_data_collective"
        or sindhi.get("dataset_id") != "cmu5wbmn400bco107vi2n2yhb"
        or sindhi.get("release") != "cv-corpus-27.0-2026-09-11"
        or sindhi.get("status") != "REFERENCE_ONLY"
        or sindhi.get("evaluation_independence") != "NOT_VERIFIED"
        or sindhi.get("test_clips") != 42
        or sindhi.get("validated_clips") != 328
        or sindhi.get("unresolved_clips") != 65569
        or sindhi.get("speaker_count") != 35
        or sindhi.get("audio_download_status") != "BLOCKED_TERMS_AND_OVERLAP_AUDIT"
    ):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)

    pashto = sources["pashto_audio_visual"]
    if (
        pashto.get("source_type") != "mozilla_data_collective"
        or pashto.get("dataset_id") != "cmuzrhfbd006l07nxoe3inrzq"
        or pashto.get("status") != "QUARANTINED_AUDIT_ONLY"
        or pashto.get("record_count") != 9421
        or pashto.get("speaker_count") != 9
        or pashto.get("speaker_population") != "educated_urban_afghanistan_age_20_35"
        or pashto.get("transcript_listening_review") != "OUTSTANDING"
        or pashto.get("consent_and_redistribution_review") != "OUTSTANDING"
        or pashto.get("evaluation_independence") != "NOT_VERIFIED"
    ):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)

    english = sources["south_asian_english"]
    if (
        english.get("status") != "SOURCE_ID_PENDING"
        or english.get("claimed_test_clips") != 3864
        or english.get("claimed_test_speakers") != 81
        or english.get("counts_verified") is not False
        or english.get("audio_download_status") != "BLOCKED_SOURCE_AUDIT"
    ):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)

    holdout = sources["sindhi_holdout_v1"]
    if (
        holdout.get("source_type") != "fresh_human_collection"
        or holdout.get("status") != "PENDING"
        or holdout.get("required_recordings") != 100
        or holdout.get("current_recordings") != 0
        or holdout.get("model_evaluation") != "NOT_RUN"
    ):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    return document


def _protocol_record(root: Path) -> dict[str, Any]:
    registry = load_registry(root)
    package = root / "src/sahulat_voice/corpora_v2"
    paths = [
        root / CONFIG_PATH,
        root / "docs/EVAL-VOICE-CORPORA-V2.md",
        root / "scripts/prepare_voice_corpora_v2.py",
        *sorted(package.glob("*.py")),
    ]
    files = {path.relative_to(root).as_posix(): file_sha256(path) for path in paths}
    record: dict[str, Any] = {
        "registry_version": "eval-voice-corpora-v2-protocol-freeze-v1",
        "protocol_id": PROTOCOL_ID,
        "protocol_sha256": record_checksum(registry["protocol"]),
        "source_registry_sha256": record_checksum(registry["sources"]),
        "status": "FROZEN_METADATA_PROTOCOL_ONLY",
        "audio_dataset_status": "NOT_FROZEN",
        "model_results": "NOT_RUN",
        "files": files,
    }
    return {**record, "registry_checksum": record_checksum(record)}


def preregister(root: Path) -> dict[str, Any]:
    record = _protocol_record(root)
    put_json(root / PROTOCOL_GATE_PATH, record)
    return verify_protocol(root)


def verify_protocol(root: Path) -> dict[str, Any]:
    expected = _protocol_record(root)
    actual = read_canonical_json(root / PROTOCOL_GATE_PATH)
    if actual != expected:
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    return expected
