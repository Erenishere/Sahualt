import re
from pathlib import Path
from typing import Any

from ..benchmark.io import (
    file_sha256,
    put_json,
    read_canonical_json,
    read_json,
    record_checksum,
)
from ..corpora_v2.audit import verify_audit
from ..corpora_v2.registry import verify_protocol as verify_base_protocol
from ..corpora_v2_readiness.analysis import verify_readiness
from ..corpora_v2_readiness.protocol import (
    PROTOCOL_GATE_PATH as READINESS_PROTOCOL_GATE_PATH,
)
from ..corpora_v2_readiness.protocol import (
    READINESS_GATE_PATH,
    READINESS_JSON_PATH,
)
from ..corpora_v2_readiness.protocol import (
    verify_protocol as verify_readiness_protocol,
)
from ..errors import ErrorCode, VoiceError

PROTOCOL_ID = "EVAL-VOICE-CORPORA-V2-MANIFEST-FREEZE"
CONFIG_PATH = "configs/voice_corpora_v2_manifest_freeze.json"
PROTOCOL_GATE_PATH = "configs/gates/eval_voice_corpora_v2_manifest_freeze_protocol_r4.json"
SUPERSEDED_PROTOCOL_GATE_PATH = (
    "configs/gates/eval_voice_corpora_v2_manifest_freeze_protocol_r3.json"
)
BASE_PROTOCOL_GATE_PATH = "configs/gates/eval_voice_corpora_v2_protocol.json"
BASE_AUDIT_GATE_PATH = "configs/gates/eval_voice_corpora_v2_audit.json"
BASE_AUDIT_PATH = "reports/eval_voice_corpora_v2_source_audit.json"
ANCHORS = {
    "base_protocol_gate_sha256": BASE_PROTOCOL_GATE_PATH,
    "base_audit_gate_sha256": BASE_AUDIT_GATE_PATH,
    "base_audit_sha256": BASE_AUDIT_PATH,
    "readiness_protocol_gate_sha256": READINESS_PROTOCOL_GATE_PATH,
    "readiness_gate_sha256": READINESS_GATE_PATH,
    "readiness_report_sha256": READINESS_JSON_PATH,
}


def _is_sha(value: object, length: int = 64) -> bool:
    return isinstance(value, str) and re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is not None


def load_config(root: Path) -> dict[str, Any]:
    document = read_json(root / CONFIG_PATH)
    if (
        not isinstance(document, dict)
        or set(document) != {"schema_version", "protocol", "anchors", "source", "outputs"}
        or document.get("schema_version") != "eval-voice-corpora-v2-manifest-freeze-v1"
    ):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    protocol = document["protocol"]
    if (
        not isinstance(protocol, dict)
        or protocol.get("id") != PROTOCOL_ID
        or protocol.get("parent_protocol_id") != "EVAL-VOICE-CORPORA-V2"
        or protocol.get("protocol_revision") != 4
        or protocol.get("status") != "PREREGISTERED_METADATA_ONLY"
        or protocol.get("seed") != 20261012
        or protocol.get("max_duration_seconds") != 30
        or protocol.get("audio_download") is not False
        or protocol.get("model_execution") is not False
        or protocol.get("training_or_tuning") is not False
        or protocol.get("transcript_policy") != "EXCLUDE_UNTIL_HUMAN_ADJUDICATED"
        or protocol.get("speaker_identity_policy") != "PUBLISHED_LABELS_ARE_NOT_VERIFIED_IDENTITIES"
        or protocol.get("amendment")
        != {
            "id": "LARGE-LEDGER-CANONICAL-READER-1",
            "supersedes_gate_path": SUPERSEDED_PROTOCOL_GATE_PATH,
            "supersedes_gate_sha256": (
                "ba8fa69f5504b3effba5a7e651d62b7f14c5b18407fdb836d7255588ddf232d9"
            ),
            "reason": (
                "Decision ledgers exceed the shared JSON reader's 2 MiB limit. Added a bounded "
                "canonical reader for frozen artifacts; the already-written R3 manifests and all "
                "source decisions remain unchanged."
            ),
            "selection_policy_changed": False,
            "readiness_rules_changed": False,
        }
    ):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    anchors = document["anchors"]
    if (
        not isinstance(anchors, dict)
        or set(anchors) != set(ANCHORS)
        or not all(_is_sha(value) for value in anchors.values())
    ):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    source = document["source"]
    subsets = source.get("subsets") if isinstance(source, dict) else None
    if (
        not isinstance(source, dict)
        or source.get("key") != "urduspeech"
        or source.get("repository") != "ASLP-lab/UrduSpeech"
        or source.get("revision") != "16dd380cfd9049a3db7f06a98e878086916bf833"
        or source.get("metadata_filename") != "clean_transcription.jsonl"
        or not isinstance(subsets, dict)
        or set(subsets) != {"standard_urdu", "code_switched", "pakistani_english"}
    ):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    expected_subsets = {
        "standard_urdu": ("ur", 200, True),
        "code_switched": ("ur-en", 200, True),
        "pakistani_english": ("en-pk", 200, False),
    }
    for key, contract in expected_subsets.items():
        record = subsets[key]
        if (
            not isinstance(record, dict)
            or set(record) != {"language", "sample_target", "required"}
            or (record.get("language"), record.get("sample_target"), record.get("required"))
            != contract
        ):
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
    outputs = document["outputs"]
    if (
        not isinstance(outputs, dict)
        or set(outputs)
        != {
            "directory",
            "selection_report_json",
            "selection_report_markdown",
            "registry",
            "protocol_gate",
            "gate",
        }
        or outputs.get("directory") != "artifacts/eval_voice_corpora_v2_manifest_freeze"
        or outputs.get("protocol_gate") != PROTOCOL_GATE_PATH
    ):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    return document


def verify_anchors(root: Path, config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or load_config(root)
    verify_base_protocol(root)
    verify_audit(root)
    verify_readiness_protocol(root)
    verify_readiness(root)
    if (
        file_sha256(root / SUPERSEDED_PROTOCOL_GATE_PATH)
        != config["protocol"]["amendment"]["supersedes_gate_sha256"]
    ):
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    for key, path in ANCHORS.items():
        if file_sha256(root / path) != config["anchors"][key]:
            raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    readiness = read_canonical_json(root / READINESS_JSON_PATH)
    if readiness.get("status") != "BLOCKED" or readiness.get("audio_downloaded") is not False:
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    return readiness


def _protocol_record(root: Path) -> dict[str, Any]:
    config = load_config(root)
    verify_anchors(root, config)
    paths = [
        root / CONFIG_PATH,
        root / "configs/voice_corpora_v2.json",
        root / "configs/voice_corpora_v2_readiness.json",
        root / "configs/eval_voice_v1.json",
        root / "configs/voice_alt_v1_models.json",
        root / "docs/EVAL-VOICE-CORPORA-V2-MANIFEST-FREEZE.md",
        root / "scripts/freeze_voice_corpora_v2_manifests.py",
        *sorted((root / "src/sahulat_voice/corpora_v2_manifest_freeze").glob("*.py")),
    ]
    files = {path.relative_to(root).as_posix(): file_sha256(path) for path in paths}
    body: dict[str, Any] = {
        "registry_version": "eval-voice-corpora-v2-manifest-freeze-protocol-v4",
        "protocol_id": PROTOCOL_ID,
        "protocol_revision": 4,
        "amendment_id": config["protocol"]["amendment"]["id"],
        "supersedes_gate_path": SUPERSEDED_PROTOCOL_GATE_PATH,
        "supersedes_gate_sha256": file_sha256(root / SUPERSEDED_PROTOCOL_GATE_PATH),
        "status": "FROZEN_METADATA_ONLY_PROTOCOL_R4",
        "audio_download": "FORBIDDEN_DURING_MANIFEST_FREEZE",
        "model_results": "NOT_RUN",
        "config_sha256": file_sha256(root / CONFIG_PATH),
        "anchors": {key: file_sha256(root / value) for key, value in ANCHORS.items()},
        "source_registry_sha256": file_sha256(root / "configs/voice_corpora_v2.json"),
        "checkpoint_registry_sha256": file_sha256(root / "configs/eval_voice_v1.json"),
        "files": files,
    }
    return {**body, "registry_checksum": record_checksum(body)}


def preregister(root: Path) -> dict[str, Any]:
    expected = _protocol_record(root)
    put_json(root / PROTOCOL_GATE_PATH, expected)
    return verify_protocol(root)


def verify_protocol(root: Path) -> dict[str, Any]:
    expected = _protocol_record(root)
    actual = read_canonical_json(root / PROTOCOL_GATE_PATH)
    if actual != expected:
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    return expected
