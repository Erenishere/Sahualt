import re
from pathlib import Path
from typing import Any

from ..benchmark.io import file_sha256, put_json, read_canonical_json, read_json, record_checksum
from ..corpora_v2.audit import verify_audit
from ..corpora_v2.registry import verify_protocol as verify_base_protocol
from ..errors import ErrorCode, VoiceError

PROTOCOL_ID = "EVAL-VOICE-CORPORA-V2"
AMENDMENT_ID = "AUDIO-ACQUISITION-READINESS-V1"
CONFIG_PATH = "configs/voice_corpora_v2_readiness.json"
PROTOCOL_GATE_PATH = "configs/gates/eval_voice_corpora_v2_readiness_protocol.json"
READINESS_GATE_PATH = "configs/gates/eval_voice_corpora_v2_readiness.json"
READINESS_JSON_PATH = "reports/eval_voice_corpora_v2_readiness.json"
READINESS_MARKDOWN_PATH = "reports/eval_voice_corpora_v2_readiness.md"

BASE_PROTOCOL_GATE_PATH = "configs/gates/eval_voice_corpora_v2_protocol.json"
BASE_AUDIT_GATE_PATH = "configs/gates/eval_voice_corpora_v2_audit.json"
BASE_AUDIT_PATH = "reports/eval_voice_corpora_v2_source_audit.json"

SOURCE_IDS = {
    "common_voice_27_sindhi",
    "pashto_audio_visual",
    "sindhi_holdout_v1",
    "south_asian_english",
    "urduspeech",
}
MODEL_IDS = {"buzzasr-sindhi", "mms-1b-all", "pashto-ghag", "whisper-large-v3"}


def _sha(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def load_config(root: Path) -> dict[str, Any]:
    document = read_json(root / CONFIG_PATH)
    if (
        not isinstance(document, dict)
        or set(document)
        != {
            "schema_version",
            "protocol",
            "sources",
            "transcript_audit",
            "speaker_overlap",
            "checkpoint_exposure",
            "readiness_criteria",
        }
        or document.get("schema_version") != "eval-voice-corpora-v2-readiness-v1"
    ):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)

    protocol = document["protocol"]
    if (
        not isinstance(protocol, dict)
        or protocol.get("id") != PROTOCOL_ID
        or protocol.get("amendment_id") != AMENDMENT_ID
        or protocol.get("status") != "PREREGISTERED_ACQUISITION_READINESS"
        or not all(
            protocol.get(key) is True
            for key in ("no_audio_download", "no_model_execution", "no_training_or_tuning")
        )
        or not all(
            _sha(protocol.get(key))
            for key in (
                "base_protocol_gate_sha256",
                "base_audit_gate_sha256",
                "base_audit_sha256",
            )
        )
    ):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)

    sources = document["sources"]
    english = sources.get("south_asian_english") if isinstance(sources, dict) else None
    if (
        not isinstance(sources, dict)
        or set(sources) != SOURCE_IDS
        or not isinstance(english, dict)
        or english.get("dataset_id") != "cmrt70sar001umm07jwxzhw89"
        or english.get("source_release") != "cv-corpus-26.0-2026-06-12"
        or english.get("declared_license") != "cc0-1.0"
        or english.get("test_clips") != 3864
        or english.get("test_speakers") != 81
        or english.get("test_hours") != 5.94
        or english.get("speaker_disjoint_splits") is not True
        or english.get("acquisition_status") != "BLOCKED_UNTIL_SELECTED_MANIFEST_FREEZE"
        or not isinstance(english.get("rights"), dict)
        or english["rights"].get("speaker_reidentification") != "FORBIDDEN"
        or english["rights"].get("redistribution") != "REHOSTING_AND_RESHARING_FORBIDDEN"
    ):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)

    urdu = sources["urduspeech"]
    if (
        urdu.get("revision") != "16dd380cfd9049a3db7f06a98e878086916bf833"
        or urdu.get("authoritative_reference") != "PENDING_HUMAN_ADJUDICATION"
        or urdu.get("mismatch_policy") != "EXCLUDE_UNTIL_HUMAN_ADJUDICATED"
        or urdu.get("acquisition_status") != "BLOCKED"
        or not isinstance(urdu.get("rights"), dict)
        or urdu["rights"].get("dataset_declared_license") != "CC-BY-4.0_ATTRIBUTION_REQUIRED"
        or urdu["rights"].get("local_asr_evaluation")
        != "PENDING_ORIGINAL_SOURCE_MEDIA_RIGHTS_REVIEW"
    ):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)

    sindhi = sources["common_voice_27_sindhi"]
    sindhi_rights = sindhi.get("rights")
    if (
        sindhi.get("dataset_id") != "cmu5wbmn400bco107vi2n2yhb"
        or sindhi.get("declared_license") != "cc0-1.0"
        or not isinstance(sindhi_rights, dict)
        or sindhi_rights.get("local_asr_evaluation") != "ALLOWED_BY_STATED_INTENDED_USE"
        or sindhi_rights.get("speaker_reidentification") != "FORBIDDEN"
        or sindhi_rights.get("rehosting") != "FORBIDDEN"
        or sindhi_rights.get("resharing") != "FORBIDDEN"
    ):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)

    pashto = sources["pashto_audio_visual"]
    pashto_rights = pashto.get("rights")
    if (
        not isinstance(pashto_rights, dict)
        or pashto_rights.get("license_scope") != "PUBLISHER_STATES_CC0_1_0"
        or pashto_rights.get("local_asr_evaluation") != "PENDING_OWNER_CONSENT_DOCUMENTATION_REVIEW"
        or pashto.get("consent_and_redistribution_review") != "OUTSTANDING"
    ):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)

    holdout_rights = sources["sindhi_holdout_v1"].get("rights")
    if (
        not isinstance(holdout_rights, dict)
        or holdout_rights.get("local_asr_evaluation")
        != "ALLOWED_ONLY_WITH_RECORDED_SPEAKER_PERMISSION"
        or holdout_rights.get("public_distribution")
        != "NOT_AUTHORIZED_WITHOUT_SEPARATE_EXPLICIT_PERMISSION_AND_LICENSE"
    ):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)

    models = document.get("checkpoint_exposure", {}).get("models")
    if not isinstance(models, dict) or set(models) != MODEL_IDS:
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    for model in models.values():
        if (
            not isinstance(model, dict)
            or re.fullmatch(r"[0-9a-f]{40}", str(model.get("revision"))) is None
            or not isinstance(model.get("source_exposure"), dict)
            or set(model["source_exposure"]) != SOURCE_IDS
        ):
            raise VoiceError(ErrorCode.INVALID_MANIFEST)

    criteria = document["readiness_criteria"]
    if (
        not isinstance(criteria, dict)
        or criteria.get("dataset_provenance_and_rights") != "BLOCKED"
        or criteria.get("selected_immutable_manifests") != "NOT_FROZEN"
        or criteria.get("sindhi_collection_protocol") != "APPROVED_DATA_PENDING"
    ):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    return document


def _verify_base_anchors(root: Path, config: dict[str, Any]) -> None:
    verify_base_protocol(root)
    verify_audit(root)
    protocol = config["protocol"]
    anchors = {
        "base_protocol_gate_sha256": BASE_PROTOCOL_GATE_PATH,
        "base_audit_gate_sha256": BASE_AUDIT_GATE_PATH,
        "base_audit_sha256": BASE_AUDIT_PATH,
    }
    if any(file_sha256(root / path) != protocol[key] for key, path in anchors.items()):
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)


def _protocol_record(root: Path) -> dict[str, Any]:
    config = load_config(root)
    _verify_base_anchors(root, config)
    package = root / "src/sahulat_voice/corpora_v2_readiness"
    paths = [
        root / CONFIG_PATH,
        root / "docs/EVAL-VOICE-CORPORA-V2-ACQUISITION.md",
        root / "docs/SINDHI-HOLDOUT-V1.md",
        root / "scripts/prepare_voice_corpora_v2_readiness.py",
        root / "scripts/sindhi_holdout_v1.py",
        root / "src/sahulat_voice/alternatives/sindhi_holdout_v1.py",
        root / "configs/sindhi_holdout_v1.input.example.json",
        root / "configs/eval_voice_v1.json",
        root / "configs/voice_alt_v1_models.json",
        *sorted(package.glob("*.py")),
    ]
    files = {path.relative_to(root).as_posix(): file_sha256(path) for path in paths}
    record: dict[str, Any] = {
        "registry_version": "eval-voice-corpora-v2-readiness-protocol-v1",
        "protocol_id": PROTOCOL_ID,
        "amendment_id": AMENDMENT_ID,
        "status": "FROZEN_ACQUISITION_READINESS_PROTOCOL",
        "audio_dataset_status": "NOT_FROZEN",
        "model_results": "NOT_RUN",
        "config_sha256": file_sha256(root / CONFIG_PATH),
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
