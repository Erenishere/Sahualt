"""Consent-gated first-party recording, freeze, and pilot ASR evaluation."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import defaultdict
from collections.abc import Callable
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from time import perf_counter
from typing import Any

from .adapters import WhisperAdapter
from .audio import read_audio
from .benchmark.io import (
    file_sha256,
    put_immutable,
    put_json,
    read_canonical_json,
    read_json,
    record_checksum,
)
from .contracts import MODEL_SPECS, ModelSpec, RuntimeSettings, parse_language
from .errors import ErrorCode, VoiceError
from .evaluation import _distance, resolve_audio_path

PROTOCOL_ID = "VOICE-BASELINE-PILOT-V1"
SOURCE_ID = "SAHULAT-FIRST-PARTY-VOICE-PILOT-V1"
INPUT_SCHEMA = "voice-baseline-pilot-recordings-v1"
CONSENT_SCHEMA = "voice-baseline-pilot-consents-v1"
MANIFEST_SCHEMA = "voice-baseline-pilot-frozen-manifest-v1"
RESULT_SCHEMA = "voice-baseline-pilot-results-v1"
ERROR_REVIEW_SCHEMA = "voice-baseline-pilot-error-reviews-v1"
NORMALIZATION_VERSION = "voice-baseline-pilot-script-normalization-v1"
LANGUAGE_GROUPS = ("ur", "ur_en", "sd", "ps")
TARGETS = {group: 30 for group in LANGUAGE_GROUPS}
MAX_RECORDINGS = 2000
MAX_TEXT_LENGTH = 4096
SPEAKER_ID = re.compile(r"SPK_[A-Za-z0-9_-]{1,32}")
SAMPLE_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
HASH = re.compile(r"[0-9a-f]{64}")
TURBO_REVISION = "41f01f3fe87f28c78e2fbf8b568835947dd65ed9"
NUMBER = re.compile(r"(?<![\w])(?:\d{1,3}(?:[,٬\u066c]\d{3})+|\d+)(?:[.٫]\d+)?(?![\w])")

CONSENT_FIELDS = {
    "speaker_id",
    "status",
    "signed_at",
    "retention_until",
    "adult_participant_confirmed",
    "form_version",
    "allowed_groups",
    "native_language_groups",
    "permissions",
    "withdrawn",
    "consent_evidence_path",
    "consent_evidence_sha256",
    "reviewer_id",
    "reviewed_at",
}
PERMISSION_FIELDS = {
    "private_audio_storage",
    "local_asr_processing",
    "aggregate_research_reporting",
    "deidentified_transcript_examples",
    "public_audio_release",
}
SAMPLE_FIELDS = {
    "sample_id",
    "speaker_id",
    "language_group",
    "audio_path",
    "audio_sha256",
    "reference_text",
    "reference_script",
    "reference_status",
    "reference_transcriber_id",
    "reference_reviewer_id",
    "reference_reviewed_at",
    "recording_source",
    "recording_source_review_status",
    "recording_reviewer_id",
    "recording_reviewed_at",
    "tts_generated",
    "recorded_at",
    "roman_urdu_reference",
    "roman_urdu_reference_status",
    "roman_urdu_reference_reviewer_id",
    "roman_urdu_reference_reviewed_at",
    "commerce_annotation",
}


def _fail() -> None:
    raise VoiceError(ErrorCode.INVALID_MANIFEST)


def _string(value: object, maximum: int = 256) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > maximum
        or any(unicodedata.category(char) == "Cs" for char in value)
    ):
        _fail()
    return value


def _iso_date(value: object) -> str:
    text = _string(value, 10)
    try:
        date.fromisoformat(text)
    except ValueError:
        _fail()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        _fail()
    return text


def _relative_file(root: Path, reference: object, suffix: str | None = None) -> Path:
    if not isinstance(reference, str) or not reference or "\\" in reference or ":" in reference:
        _fail()
    relative = PurePosixPath(reference)
    if relative.is_absolute() or ".." in relative.parts or relative.as_posix() != reference:
        _fail()
    if suffix and relative.suffix.lower() != suffix:
        _fail()
    try:
        resolved = (root / Path(*relative.parts)).resolve(strict=True)
        if not resolved.is_relative_to(root.resolve()):
            _fail()
        if not resolved.is_file():
            _fail()
        return resolved
    except (OSError, RuntimeError, ValueError):
        _fail()
    raise AssertionError("unreachable")


def detect_script(text: str) -> str:
    latin = arabic = False
    for char in text:
        name = unicodedata.name(char, "")
        latin |= "LATIN" in name and char.isalpha()
        arabic |= ("ARABIC" in name or "PERSIAN" in name) and char.isalpha()
    if latin and arabic:
        return "mixed"
    if latin:
        return "latin"
    if arabic:
        return "arabic"
    return "unknown"


def normalize_for_scoring(text: str, language_group: str) -> str:
    if language_group not in LANGUAGE_GROUPS or not isinstance(text, str):
        _fail()
    normalized = unicodedata.normalize("NFC", text).casefold().replace("ـ", "")
    normalized = "".join(
        str(unicodedata.digit(char)) if char.isdigit() else char for char in normalized
    )
    normalized = re.sub(r"(?<=\d)[,٬\u066c](?=\d)", "", normalized)
    normalized = re.sub(r"(?<=\d)[٫](?=\d)", ".", normalized)
    normalized = "".join(
        " " if unicodedata.category(char).startswith("P") else char for char in normalized
    )
    return " ".join(normalized.split())


def score_text(reference: str, hypothesis: str, language_group: str) -> dict[str, int | float]:
    expected = normalize_for_scoring(reference, language_group)
    actual = normalize_for_scoring(hypothesis, language_group)
    if not expected:
        _fail()
    word_errors = _distance(expected.split(), actual.split())
    character_errors = _distance(list(expected), list(actual))
    return {
        "reference_words": len(expected.split()),
        "reference_characters": len(expected),
        "word_errors": word_errors,
        "character_errors": character_errors,
        "wer": word_errors / len(expected.split()),
        "cer": character_errors / len(expected),
    }


def _validate_consent_registry(
    document: Any, evidence_root: Path
) -> tuple[dict[str, dict[str, Any]], str]:
    if (
        not isinstance(document, dict)
        or set(document) != {"schema_version", "source_id", "consents"}
        or document["schema_version"] != CONSENT_SCHEMA
        or document["source_id"] != SOURCE_ID
        or not isinstance(document["consents"], list)
    ):
        _fail()
    consents: dict[str, dict[str, Any]] = {}
    for record in document["consents"]:
        if not isinstance(record, dict) or set(record) != CONSENT_FIELDS:
            _fail()
        sid = _string(record["speaker_id"], 40)
        permissions = record["permissions"]
        allowed = record["allowed_groups"]
        native = record["native_language_groups"]
        if (
            not SPEAKER_ID.fullmatch(sid)
            or sid in consents
            or record["status"] != "active"
            or record["withdrawn"] is not False
            or record["adult_participant_confirmed"] is not True
            or record["form_version"] != "VOICE-BASELINE-PILOT-CONSENT-V1"
            or not isinstance(permissions, dict)
            or set(permissions) != PERMISSION_FIELDS
            or any(type(value) is not bool for value in permissions.values())
            or permissions["private_audio_storage"] is not True
            or permissions["local_asr_processing"] is not True
            or permissions["aggregate_research_reporting"] is not True
            or permissions["public_audio_release"] is not False
            or not isinstance(allowed, list)
            or not isinstance(native, list)
            or any(group not in LANGUAGE_GROUPS for group in allowed + native)
            or len(allowed) != len(set(allowed))
            or len(native) != len(set(native))
            or not set(native) <= set(allowed)
        ):
            _fail()
        signed_at = _iso_date(record["signed_at"])
        retention_until = _iso_date(record["retention_until"])
        reviewed_at = _iso_date(record["reviewed_at"])
        if date.fromisoformat(reviewed_at) < date.fromisoformat(signed_at) or date.fromisoformat(
            retention_until
        ) < date.fromisoformat(signed_at):
            _fail()
        _string(record["reviewer_id"], 64)
        evidence_hash = record["consent_evidence_sha256"]
        if not isinstance(evidence_hash, str) or not HASH.fullmatch(evidence_hash):
            _fail()
        evidence_path = _relative_file(evidence_root, record["consent_evidence_path"])
        if file_sha256(evidence_path) != evidence_hash:
            raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
        consents[sid] = dict(record)
    return consents, record_checksum(document)


def _validate_commerce(
    value: object, reference_text: str, language_group: str
) -> dict[str, Any] | None:
    if value is None:
        return None
    fields = {"intent_label", "intent_cues", "brand_names", "prices", "reviewer_id", "reviewed_at"}
    if not isinstance(value, dict) or set(value) != fields:
        _fail()
    intent = value["intent_label"]
    cues, brands, prices = value["intent_cues"], value["brand_names"], value["prices"]
    if (
        intent not in {"product_search", "price_check", "availability_check", "other"}
        or not isinstance(cues, list)
        or not isinstance(brands, list)
        or not isinstance(prices, list)
        or any(not isinstance(item, str) or not item.strip() for item in cues + brands)
    ):
        _fail()
    if any(not _contains_surface(reference_text, item, language_group) for item in cues + brands):
        _fail()
    for item in prices:
        if not isinstance(item, dict) or set(item) != {
            "amount_major",
            "currency",
            "spoken_forms",
        }:
            _fail()
        amount = item["amount_major"]
        spoken_forms = item["spoken_forms"]
        if (
            not isinstance(amount, str)
            or not re.fullmatch(r"\d{1,12}(?:\.\d{1,2})?", amount)
            or item["currency"] != "PKR"
            or not isinstance(spoken_forms, list)
            or not spoken_forms
            or any(
                not isinstance(form, str)
                or not _contains_surface(reference_text, form, language_group)
                for form in spoken_forms
            )
        ):
            _fail()
        target = format(Decimal(amount).normalize(), "f")
        digit_values = set().union(*(_number_values(form) for form in spoken_forms))
        if digit_values and target not in digit_values:
            _fail()
    _string(value["reviewer_id"], 64)
    _iso_date(value["reviewed_at"])
    if not cues and not brands and not prices:
        _fail()
    return dict(value)


def validate_bundle(
    input_document: Any,
    consent_document: Any,
    audio_root: Path,
    evidence_root: Path,
) -> dict[str, Any]:
    if (
        not isinstance(input_document, dict)
        or set(input_document) != {"schema_version", "source_id", "recordings"}
        or input_document["schema_version"] != INPUT_SCHEMA
        or input_document["source_id"] != SOURCE_ID
        or not isinstance(input_document["recordings"], list)
        or len(input_document["recordings"]) > MAX_RECORDINGS
    ):
        _fail()
    consents, consent_sha256 = _validate_consent_registry(consent_document, evidence_root)
    seen_ids: set[str] = set()
    seen_audio: set[str] = set()
    checked: list[dict[str, Any]] = []
    for source_record in input_document["recordings"]:
        if not isinstance(source_record, dict) or set(source_record) != SAMPLE_FIELDS:
            _fail()
        item = dict(source_record)
        sid = item["speaker_id"]
        sample_id = item["sample_id"]
        group = item["language_group"]
        if (
            not isinstance(sid, str)
            or not SPEAKER_ID.fullmatch(sid)
            or not isinstance(sample_id, str)
            or not SAMPLE_ID.fullmatch(sample_id)
            or sample_id in seen_ids
            or group not in LANGUAGE_GROUPS
            or sid not in consents
            or group not in consents[sid]["allowed_groups"]
            or item["recording_source"] != "fresh_human_recording"
            or item["recording_source_review_status"] != "human_verified"
            or item["tts_generated"] is not False
            or item["reference_status"] != "human_verified"
            or not isinstance(item["reference_text"], str)
            or not item["reference_text"].strip()
            or len(item["reference_text"]) > MAX_TEXT_LENGTH
            or item["reference_script"] not in {"arabic", "latin", "mixed"}
            or detect_script(item["reference_text"]) != item["reference_script"]
        ):
            _fail()
        consent = consents[sid]
        if consent["withdrawn"] is not False or consent["status"] != "active":
            _fail()
        if date.fromisoformat(consent["retention_until"]) < date.today():
            _fail()
        _string(item["reference_reviewer_id"], 64)
        _string(item["reference_transcriber_id"], 64)
        _string(item["recording_reviewer_id"], 64)
        if item["reference_transcriber_id"] == item["reference_reviewer_id"]:
            _fail()
        recording_reviewed_at = _iso_date(item["recording_reviewed_at"])
        recorded_at = _iso_date(item["recorded_at"])
        reference_reviewed_at = _iso_date(item["reference_reviewed_at"])
        if not (
            date.fromisoformat(consents[sid]["signed_at"])
            <= date.fromisoformat(recorded_at)
            <= date.fromisoformat(recording_reviewed_at)
            <= date.fromisoformat(reference_reviewed_at)
            <= date.fromisoformat(consents[sid]["retention_until"])
        ):
            _fail()
        checksum = item["audio_sha256"]
        if not isinstance(checksum, str) or not HASH.fullmatch(checksum) or checksum in seen_audio:
            _fail()
        audio_path = _relative_file(audio_root, item["audio_path"], ".wav")
        audio = read_audio(audio_path)
        if audio.sha256 != checksum:
            raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
        if not normalize_for_scoring(item["reference_text"], group):
            _fail()
        roman = item["roman_urdu_reference"]
        roman_fields = (
            item["roman_urdu_reference_status"],
            item["roman_urdu_reference_reviewer_id"],
            item["roman_urdu_reference_reviewed_at"],
        )
        if roman is None:
            if roman_fields != (None, None, None):
                _fail()
        elif (
            group not in {"ur", "ur_en"}
            or not isinstance(roman, str)
            or not roman.strip()
            or len(roman) > MAX_TEXT_LENGTH
            or detect_script(roman) != "latin"
            or item["roman_urdu_reference_status"] != "human_verified"
        ):
            _fail()
        else:
            _string(item["roman_urdu_reference_reviewer_id"], 64)
            _iso_date(item["roman_urdu_reference_reviewed_at"])
        item["commerce_annotation"] = _validate_commerce(
            item["commerce_annotation"], item["reference_text"], group
        )
        item["consent_record_sha256"] = record_checksum(
            {key: value for key, value in consent.items() if key != "consent_evidence_path"}
        )
        item["native_language_attested"] = group in consent["native_language_groups"]
        item["error_example_permission"] = consent["permissions"][
            "deidentified_transcript_examples"
        ]
        seen_ids.add(sample_id)
        seen_audio.add(checksum)
        checked.append(item)
    selected, selection_audit = deterministic_selection(checked)
    counts = {
        group: {
            "eligible_recordings": sum(row["language_group"] == group for row in checked),
            "selected_recordings": sum(row["language_group"] == group for row in selected),
            "speaker_count": len(
                {row["speaker_id"] for row in selected if row["language_group"] == group}
            ),
            "native_speaker_count": len(
                {
                    row["speaker_id"]
                    for row in selected
                    if row["language_group"] == group and row["native_language_attested"]
                }
            ),
        }
        for group in LANGUAGE_GROUPS
    }
    return {
        "source_id": SOURCE_ID,
        "input_sha256": record_checksum(input_document),
        "consent_registry_sha256": consent_sha256,
        "eligible_recordings": sorted(checked, key=lambda row: row["sample_id"]),
        "selected_recordings": sorted(selected, key=lambda row: row["sample_id"]),
        "selection_audit": selection_audit,
        "counts": counts,
        "status": "PENDING_RECORDINGS" if not checked else "VALIDATED_NOT_FROZEN",
    }


def deterministic_selection(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    for group in LANGUAGE_GROUPS:
        bucket = [row for row in records if row["language_group"] == group]
        speakers: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in bucket:
            speakers[row["speaker_id"]].append(row)

        def order_key(value: str, language_group: str = group) -> str:
            key = f"{PROTOCOL_ID}|{language_group}|{value}"
            return hashlib.sha256(key.encode()).hexdigest()

        speaker_ids = sorted(speakers, key=lambda value: (order_key(value), value))
        for sid in speaker_ids:
            speakers[sid].sort(key=lambda row: (order_key(row["sample_id"]), row["sample_id"]))
        ordered: list[dict[str, Any]] = []
        depth = 0
        while len(ordered) < len(bucket):
            added = False
            for sid in speaker_ids:
                if depth < len(speakers[sid]):
                    ordered.append(speakers[sid][depth])
                    added = True
            if not added:
                break
            depth += 1
        chosen = ordered[: TARGETS[group]]
        chosen_ids = {row["sample_id"] for row in chosen}
        selected.extend(chosen)
        rank = {row["sample_id"]: position for position, row in enumerate(chosen, 1)}
        for row in sorted(bucket, key=lambda sample: sample["sample_id"]):
            audit.append(
                {
                    "sample_id": row["sample_id"],
                    "language_group": group,
                    "decision": "SELECTED"
                    if row["sample_id"] in chosen_ids
                    else "NOT_SELECTED_TARGET_CAP",
                    "selection_rank": rank.get(row["sample_id"]),
                }
            )
    return selected, audit


def _model_config(root: Path) -> dict[str, Any]:
    protocol = read_json(root / "configs/voice_baseline_pilot_v1.json")
    if (
        protocol.get("schema_version") != "voice-baseline-pilot-protocol-v1"
        or protocol.get("protocol_id") != PROTOCOL_ID
        or set(protocol.get("model_matrix", {})) != set(LANGUAGE_GROUPS)
        or set(protocol.get("models", {}))
        != {"whisper-large-v3-turbo", "mms-1b-all", "buzzasr-sindhi", "pashto-ghag"}
    ):
        _fail()
    expected_matrix = {
        "ur": ["whisper-large-v3-turbo"],
        "ur_en": ["whisper-large-v3-turbo"],
        "sd": ["mms-1b-all", "buzzasr-sindhi"],
        "ps": ["mms-1b-all", "pashto-ghag"],
    }
    if protocol["model_matrix"] != expected_matrix:
        _fail()
    pins = protocol["models"]
    if (
        pins["whisper-large-v3-turbo"]["repository"] != "openai/whisper-large-v3-turbo"
        or pins["whisper-large-v3-turbo"]["revision"] != TURBO_REVISION
        or pins["whisper-large-v3-turbo"]["license"] != "mit"
    ):
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    old = read_json(root / "configs/eval_voice_v1.json")["models"]["mms"]
    if (pins["mms-1b-all"]["repository"], pins["mms-1b-all"]["revision"]) != (
        old["repository"],
        old["revision"],
    ) or pins["mms-1b-all"]["license"] != MODEL_SPECS["mms"].license:
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    alternatives = read_json(root / "configs/voice_alt_v1_models.json")["models"]
    for pilot_key, existing_key in (
        ("buzzasr-sindhi", "buzzasr-sindhi"),
        ("pashto-ghag", "pashto-ghag"),
    ):
        existing = alternatives[existing_key]
        if (pins[pilot_key]["repository"], pins[pilot_key]["revision"]) != (
            existing["repository"],
            existing["revision"],
        ) or pins[pilot_key]["license"] != existing["license"]:
            raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    return protocol


def freeze_bundle(
    root: Path,
    input_document: Any,
    consent_document: Any,
    audio_root: Path,
    evidence_root: Path,
    workspace: Path | None = None,
) -> dict[str, Any]:
    validated = validate_bundle(input_document, consent_document, audio_root, evidence_root)
    if not validated["selected_recordings"]:
        return {"status": "PENDING_RECORDINGS", "counts": validated["counts"]}
    protocol = _model_config(root)
    protocol_sha = file_sha256(root / "configs/voice_baseline_pilot_v1.json")
    source_registry_sha = file_sha256(root / "configs/corpora/voice_baseline_pilot_v1.json")
    frozen_samples: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    audio_payloads: dict[str, bytes] = {}
    workspace = workspace or root / ".local/voice_baseline_pilot_v1"
    frozen_dir = workspace / "frozen"
    for row in validated["selected_recordings"]:
        source = resolve_audio_path(audio_root, row["audio_path"])
        payload = source.read_bytes()
        if hashlib.sha256(payload).hexdigest() != row["audio_sha256"]:
            raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
        relative = f"audio/{row['sample_id']}.wav"
        audio_payloads[relative] = payload
        record = {key: value for key, value in row.items() if key != "audio_path"}
        record["audio_path"] = relative
        frozen_samples.append(record)
        files.append({"path": relative, "sha256": row["audio_sha256"], "size_bytes": len(payload)})
    payload = {
        "schema_version": MANIFEST_SCHEMA,
        "protocol_id": PROTOCOL_ID,
        "source_id": SOURCE_ID,
        "protocol_sha256": protocol_sha,
        "source_registry_sha256": source_registry_sha,
        "input_sha256": validated["input_sha256"],
        "consent_registry_sha256": validated["consent_registry_sha256"],
        "normalization_version": NORMALIZATION_VERSION,
        "selection_algorithm": protocol["selection"]["algorithm"],
        "selection_audit": validated["selection_audit"],
        "counts": validated["counts"],
        "samples": sorted(frozen_samples, key=lambda row: row["sample_id"]),
        "files": sorted(files, key=lambda row: row["path"]),
        "model_matrix": protocol["model_matrix"],
        "status": "FROZEN_PILOT",
    }
    manifest_sha = record_checksum(payload)
    destination = frozen_dir / manifest_sha
    destination.mkdir(parents=True, exist_ok=True)
    for relative, audio_payload in audio_payloads.items():
        put_immutable(destination / relative, audio_payload)
    put_json(destination / "manifest.json", payload)
    put_json(
        destination / "manifest.registry.json",
        {"manifest_sha256": manifest_sha, "sample_count": len(frozen_samples)},
    )
    verify_frozen(destination)
    return {
        "status": "FROZEN_PILOT",
        "manifest_sha256": manifest_sha,
        "manifest_path": str(destination / "manifest.json"),
        "counts": validated["counts"],
    }


def verify_frozen(directory: Path, root: Path | None = None) -> dict[str, Any]:
    manifest_path = directory / "manifest.json"
    document = read_canonical_json(manifest_path)
    expected = read_canonical_json(directory / "manifest.registry.json")
    manifest_sha = record_checksum(document)
    if (
        document.get("schema_version") != MANIFEST_SCHEMA
        or document.get("protocol_id") != PROTOCOL_ID
        or document.get("source_id") != SOURCE_ID
        or expected != {"manifest_sha256": manifest_sha, "sample_count": len(document["samples"])}
        or directory.name != manifest_sha
    ):
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    if root is not None and (
        document["protocol_sha256"] != file_sha256(root / "configs/voice_baseline_pilot_v1.json")
        or document["source_registry_sha256"]
        != file_sha256(root / "configs/corpora/voice_baseline_pilot_v1.json")
    ):
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    seen: set[str] = set()
    for sample in document["samples"]:
        path = resolve_audio_path(directory, sample["audio_path"])
        audio = read_audio(path)
        if audio.sha256 != sample["audio_sha256"] or audio.sha256 in seen:
            raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
        seen.add(audio.sha256)
    if sorted(document["files"], key=lambda row: row["path"]) != sorted(
        [
            {
                "path": sample["audio_path"],
                "sha256": sample["audio_sha256"],
                "size_bytes": (directory / sample["audio_path"]).stat().st_size,
            }
            for sample in document["samples"]
        ],
        key=lambda row: row["path"],
    ):
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    return {"status": "FROZEN_VERIFIED", "manifest_sha256": manifest_sha, "sample_count": len(seen)}


def verify_active_consent(manifest: dict[str, Any], workspace: Path) -> None:
    consent_document = read_json(workspace / "consent_registry.json")
    _, consent_sha = _validate_consent_registry(consent_document, workspace / "consent-evidence")
    if consent_sha != manifest["consent_registry_sha256"]:
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    used_speakers = {sample["speaker_id"] for sample in manifest["samples"]}
    if any(
        record["speaker_id"] in used_speakers
        and date.fromisoformat(record["retention_until"]) < date.today()
        for record in consent_document["consents"]
    ):
        raise VoiceError(ErrorCode.INVALID_CONFIG)


def _number_values(text: str) -> set[str]:
    converted = "".join(str(unicodedata.digit(char)) if char.isdigit() else char for char in text)
    results: set[str] = set()
    for match in NUMBER.finditer(converted):
        value = (
            match.group().replace(",", "").replace("٬", "").replace("\u066c", "").replace("٫", ".")
        )
        try:
            results.add(format(Decimal(value).normalize(), "f"))
        except InvalidOperation:
            continue
    return results


def _contains_surface(hypothesis: str, surface: str, group: str) -> bool:
    expected = normalize_for_scoring(surface, group)
    actual = normalize_for_scoring(hypothesis, group)
    return bool(expected) and f" {expected} " in f" {actual} "


def _edit_metrics(reference: str, hypothesis: str, group: str) -> dict[str, Any]:
    expected = normalize_for_scoring(reference, group)
    actual = normalize_for_scoring(hypothesis, group)
    words, chars = expected.split(), list(expected)
    return {
        "reference_words": len(words),
        "reference_characters": len(chars),
        "word_errors": _distance(words, actual.split()),
        "character_errors": _distance(chars, list(actual)),
        "normalized_reference": expected,
        "normalized_hypothesis": actual,
    }


def _empty_commerce() -> dict[str, int]:
    return {
        "annotated_samples": 0,
        "intent_cues": 0,
        "intent_cues_preserved": 0,
        "brand_mentions": 0,
        "brand_mentions_preserved": 0,
        "price_mentions": 0,
        "price_amounts_recognized": 0,
    }


def _commerce_counts(
    samples: list[dict[str, Any]], hypotheses: dict[str, str], group: str
) -> dict[str, Any]:
    counts = _empty_commerce()
    for sample in samples:
        annotation = sample["commerce_annotation"]
        if annotation is None:
            continue
        counts["annotated_samples"] += 1
        hypothesis = hypotheses.get(sample["sample_id"], "")
        for cue in annotation["intent_cues"]:
            counts["intent_cues"] += 1
            counts["intent_cues_preserved"] += int(_contains_surface(hypothesis, cue, group))
        for brand in annotation["brand_names"]:
            counts["brand_mentions"] += 1
            counts["brand_mentions_preserved"] += int(_contains_surface(hypothesis, brand, group))
        extracted = _number_values(hypothesis)
        for price in annotation["prices"]:
            counts["price_mentions"] += 1
            target = format(Decimal(price["amount_major"]).normalize(), "f")
            counts["price_amounts_recognized"] += int(target in extracted)
    return {
        **counts,
        "intent_cue_preservation_rate": (
            counts["intent_cues_preserved"] / counts["intent_cues"]
            if counts["intent_cues"]
            else None
        ),
        "brand_exact_preservation_rate": (
            counts["brand_mentions_preserved"] / counts["brand_mentions"]
            if counts["brand_mentions"]
            else None
        ),
        "price_amount_recognition_rate": (
            counts["price_amounts_recognized"] / counts["price_mentions"]
            if counts["price_mentions"]
            else None
        ),
        "intent_classification_accuracy": None,
        "intent_classification_note": (
            "No downstream intent classifier is in this ASR pilot; "
            "only annotated cue preservation is measured."
        ),
    }


def summarize_group(
    samples: list[dict[str, Any]], results: list[dict[str, Any]], group: str
) -> dict[str, Any]:
    matching = [row for row in results if row["language_group"] == group]
    by_id = {row["sample_id"]: row for row in matching}
    reference_words = sum(row["scoring"]["reference_words"] for row in matching)
    reference_chars = sum(row["scoring"]["reference_characters"] for row in matching)
    word_errors = sum(row["scoring"]["word_errors"] for row in matching)
    char_errors = sum(row["scoring"]["character_errors"] for row in matching)
    latencies = [row["latency_ms"] for row in matching if row["latency_ms"] is not None]
    ordered = sorted(latencies)
    latency_summary = None
    if ordered:
        latency_summary = {
            "mean": sum(ordered) / len(ordered),
            "median": ordered[(len(ordered) - 1) // 2]
            if len(ordered) % 2
            else (ordered[len(ordered) // 2 - 1] + ordered[len(ordered) // 2]) / 2,
            "p95": ordered[max(0, (95 * len(ordered) + 99) // 100 - 1)],
            "unit": "milliseconds_per_recording",
            "population": "scored_calls; model_load_and_unscored_warmup_reported_separately",
        }
    hypotheses = {row["sample_id"]: row["hypothesis_text"] or "" for row in matching}
    roman_samples = [
        sample
        for sample in samples
        if sample["language_group"] == group and sample["roman_urdu_reference"]
    ]
    roman_scores = []
    for sample in roman_samples:
        result = by_id[sample["sample_id"]]
        roman_scores.append(
            score_text(sample["roman_urdu_reference"], result["hypothesis_text"] or "", group)
        )
    scripts = [row["hypothesis_script"] for row in matching if row["status"] == "SUCCESS"]
    return {
        "sample_count": len(matching),
        "speaker_count": len({row["speaker_id"] for row in matching}),
        "native_speaker_count": len(
            {row["speaker_id"] for row in matching if row["native_language_attested"]}
        ),
        "successful_transcriptions": sum(row["status"] == "SUCCESS" for row in matching),
        "failed_transcriptions": sum(row["status"] == "FAILED" for row in matching),
        "failed_transcription_rate": sum(row["status"] == "FAILED" for row in matching)
        / len(matching)
        if matching
        else None,
        "wer": word_errors / reference_words if reference_words else None,
        "cer": char_errors / reference_chars if reference_chars else None,
        "word_errors": word_errors,
        "character_errors": char_errors,
        "reference_words": reference_words,
        "reference_characters": reference_chars,
        "latency_ms": latency_summary,
        "model_load_ms": matching[0]["model_load_ms"] if matching else None,
        "unscored_warmup_ms": matching[0]["warmup_ms"] if matching else None,
        "hypothesis_script_counts": {
            profile: scripts.count(profile) for profile in ("arabic", "latin", "mixed", "unknown")
        },
        "script_match_count": sum(
            row["script_match"] for row in matching if row["status"] == "SUCCESS"
        ),
        "script_match_rate": (
            sum(row["script_match"] for row in matching if row["status"] == "SUCCESS")
            / sum(row["status"] == "SUCCESS" for row in matching)
            if any(row["status"] == "SUCCESS" for row in matching)
            else None
        ),
        "roman_urdu_reference_count": len(roman_scores),
        "roman_urdu_wer": (
            sum(score["word_errors"] for score in roman_scores)
            / sum(score["reference_words"] for score in roman_scores)
            if roman_scores and sum(score["reference_words"] for score in roman_scores)
            else None
        ),
        "roman_urdu_cer": (
            sum(score["character_errors"] for score in roman_scores)
            / sum(score["reference_characters"] for score in roman_scores)
            if roman_scores and sum(score["reference_characters"] for score in roman_scores)
            else None
        ),
        "commerce": _commerce_counts(samples, hypotheses, group),
    }


def _make_adapter(root: Path, model_id: str):
    if model_id == "mms-1b-all":
        from .adapters import create_adapter

        return create_adapter("mms", RuntimeSettings(device="cpu", local_files_only=True))
    if model_id == "whisper-large-v3-turbo":
        return PilotWhisperTurboAdapter()
    from .alternatives.adapters import SpecialistWhisperAdapter
    from .alternatives.metadata import verified_assets

    key = "buzzasr-sindhi" if model_id == "buzzasr-sindhi" else "pashto-ghag"
    verified_assets(root, key)
    return SpecialistWhisperAdapter(root, key)


class PilotWhisperTurboAdapter(WhisperAdapter):
    """Whisper adapter scoped to the pilot's own turbo pin; does not touch V1's adapter."""

    spec = ModelSpec(
        "whisper-large-v3-turbo",
        "openai/whisper-large-v3-turbo",
        TURBO_REVISION,
        "mit",
    )

    def __init__(self) -> None:
        super().__init__(RuntimeSettings(device="cpu", local_files_only=True))

    def _load(self) -> None:
        if self._model is not None:
            return
        start = perf_counter()
        try:
            import torch
            from transformers import AutoProcessor, WhisperForConditionalGeneration

            options = {
                "revision": self.spec.revision,
                "local_files_only": True,
                "trust_remote_code": False,
                "token": False,
            }
            processor = AutoProcessor.from_pretrained(self.spec.repository, **options)
            model = WhisperForConditionalGeneration.from_pretrained(
                self.spec.repository,
                **options,
                use_safetensors=True,
                dtype=torch.float32,
            )
            model.to("cpu").eval().requires_grad_(False)
        except Exception:
            raise VoiceError(ErrorCode.MODEL_UNAVAILABLE) from None
        self._processor, self._model = processor, model
        self.load_time_ms = (perf_counter() - start) * 1000


def run_evaluation(
    root: Path,
    manifest_directory: Path,
    adapter_factory: Callable[[Path, str], Any] | None = None,
    workspace: Path | None = None,
) -> dict[str, Any]:
    frozen = verify_frozen(manifest_directory, root)
    manifest = read_canonical_json(manifest_directory / "manifest.json")
    workspace = workspace or root / ".local/voice_baseline_pilot_v1"
    verify_active_consent(manifest, workspace)
    protocol = _model_config(root)
    factory = adapter_factory or _make_adapter
    records_by_group = {
        group: [sample for sample in manifest["samples"] if sample["language_group"] == group]
        for group in LANGUAGE_GROUPS
    }
    model_results: dict[str, Any] = {}
    for group in LANGUAGE_GROUPS:
        for model_id in protocol["model_matrix"][group]:
            samples = records_by_group[group]
            if not samples:
                continue
            try:
                adapter = factory(root, model_id)
                load_start = perf_counter()
                adapter._load()
                load_ms = (
                    float(getattr(adapter, "load_time_ms", 0.0))
                    or (perf_counter() - load_start) * 1000
                )
                first = samples[0]
                first_audio = read_audio(
                    resolve_audio_path(manifest_directory, first["audio_path"])
                )
                warm_start = perf_counter()
                adapter.transcribe(first_audio, parse_language("ur" if group == "ur_en" else group))
                warmup_ms = (perf_counter() - warm_start) * 1000
            except VoiceError as error:
                model_results[f"{model_id}:{group}"] = {
                    "model_id": model_id,
                    "model_pin": protocol["models"][model_id],
                    "language_group": group,
                    "status": "MODEL_UNAVAILABLE",
                    "failure_code": error.code.value,
                    "summary": None,
                    "records": [],
                }
                continue
            outputs: list[dict[str, Any]] = []
            for sample in samples:
                audio = read_audio(resolve_audio_path(manifest_directory, sample["audio_path"]))
                if audio.sha256 != sample["audio_sha256"]:
                    raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
                language = parse_language("ur" if group == "ur_en" else group)
                started = perf_counter()
                status, failure_code, hypothesis = "SUCCESS", None, None
                try:
                    hypothesis = adapter.transcribe(audio, language)
                    if not isinstance(hypothesis, str) or not hypothesis.strip():
                        raise VoiceError(ErrorCode.EMPTY_TRANSCRIPT)
                except VoiceError as error:
                    status, failure_code, hypothesis = "FAILED", error.code.value, ""
                latency_ms = (perf_counter() - started) * 1000
                scoring = score_text(sample["reference_text"], hypothesis, group)
                raw_script = detect_script(hypothesis)
                profile = "unknown" if raw_script == "unknown" else raw_script
                roman_score = (
                    score_text(sample["roman_urdu_reference"], hypothesis, group)
                    if sample["roman_urdu_reference"] is not None
                    else None
                )
                outputs.append(
                    {
                        "sample_id": sample["sample_id"],
                        "speaker_id": sample["speaker_id"],
                        "language_group": group,
                        "status": status,
                        "failure_code": failure_code,
                        "reference_text": sample["reference_text"],
                        "hypothesis_text": hypothesis,
                        "reference_script": sample["reference_script"],
                        "hypothesis_script": profile,
                        "script_match": raw_script == sample["reference_script"],
                        "scoring": scoring,
                        "roman_urdu_scoring": roman_score,
                        "latency_ms": latency_ms,
                        "model_load_ms": load_ms,
                        "warmup_ms": warmup_ms,
                        "native_language_attested": sample["native_language_attested"],
                        "reference_transcriber_id": sample["reference_transcriber_id"],
                        "reference_reviewer_id": sample["reference_reviewer_id"],
                        "recording_reviewer_id": sample["recording_reviewer_id"],
                        "commerce_annotation": sample["commerce_annotation"],
                        "error_example_permission": sample["error_example_permission"],
                    }
                )
            model_results[f"{model_id}:{group}"] = {
                "model_id": model_id,
                "model_pin": protocol["models"][model_id],
                "language_group": group,
                "status": "COMPLETED",
                "summary": summarize_group(samples, outputs, group),
                "records": outputs,
            }
    strongest: dict[str, Any] = {}
    for group in LANGUAGE_GROUPS:
        configured_count = len(protocol["model_matrix"][group])
        options = [
            result
            for result in model_results.values()
            if result["language_group"] == group
            and result["status"] == "COMPLETED"
            and result["summary"]["wer"] is not None
        ]
        if not options:
            strongest[group] = {"model_id": None, "status": "NO_COMPLETED_MODEL"}
            continue
        options.sort(
            key=lambda row: (row["summary"]["wer"], row["summary"]["cer"], row["model_id"])
        )
        tied = [
            option
            for option in options
            if (option["summary"]["wer"], option["summary"]["cer"])
            == (options[0]["summary"]["wer"], options[0]["summary"]["cer"])
        ]
        strongest[group] = {
            "model_id": tied[0]["model_id"] if len(tied) == 1 else None,
            "tied_models": [row["model_id"] for row in tied],
            "status": (
                "SINGLE_CONFIGURED_MODEL_MEASURED"
                if configured_count == 1
                else "ONE_MODEL_COMPLETED_COMPARISON_INCOMPLETE"
                if len(options) == 1
                else "PILOT_LOWEST_WER_CER"
                if len(tied) == 1
                else "PILOT_TIE"
            ),
            "basis": (
                "only configured model; no head-to-head comparison"
                if configured_count == 1
                else "only one configured candidate completed; no head-to-head comparison"
                if len(options) == 1
                else "lowest pooled micro-WER, then pooled micro-CER; "
                "descriptive pilot comparison only"
            ),
        }
    result_payload = {
        "schema_version": RESULT_SCHEMA,
        "protocol_id": PROTOCOL_ID,
        "label": "PILOT",
        "production_promotion": False,
        "v1_replacement": False,
        "manifest_sha256": frozen["manifest_sha256"],
        "protocol_sha256": file_sha256(root / "configs/voice_baseline_pilot_v1.json"),
        "execution_date": date.today().isoformat(),
        "normalization_version": NORMALIZATION_VERSION,
        "collection_counts": manifest["counts"],
        "model_results": model_results,
        "strongest_model_by_language": strongest,
        "limitations": [
            "Small, first-party convenience sample; not production-grade.",
            "Speaker pseudonyms are collection labels, not verified identities.",
            (
                "Urdu and Urdu-English groups have only the configured Whisper model, "
                "so no head-to-head model winner is possible there."
            ),
            "Commerce intent is cue-preservation only; no NLU classifier is evaluated.",
            (
                "Model training exposure to utterance text and common phrases "
                "is not independently established."
            ),
        ],
    }
    return result_payload


def error_review_template(manifest_sha256: str) -> dict[str, Any]:
    return {
        "schema_version": ERROR_REVIEW_SCHEMA,
        "protocol_id": PROTOCOL_ID,
        "manifest_sha256": manifest_sha256,
        "reviews": [],
    }


def validate_error_reviews(
    result: dict[str, Any], review_document: Any
) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, int]]:
    if (
        not isinstance(review_document, dict)
        or set(review_document) != {"schema_version", "protocol_id", "manifest_sha256", "reviews"}
        or review_document["schema_version"] != ERROR_REVIEW_SCHEMA
        or review_document["protocol_id"] != PROTOCOL_ID
        or review_document["manifest_sha256"] != result["manifest_sha256"]
        or not isinstance(review_document["reviews"], list)
    ):
        _fail()
    predictions: dict[tuple[str, str], dict[str, Any]] = {}
    for model in result["model_results"].values():
        for record in model.get("records", []):
            predictions[(model["model_id"], record["sample_id"])] = record
    reviews: dict[tuple[str, str], dict[str, Any]] = {}
    counts = {"approved": 0, "rejected": 0}
    for review in review_document["reviews"]:
        if not isinstance(review, dict) or set(review) != {
            "model_id",
            "sample_id",
            "decision",
            "reviewer_id",
            "reviewed_at",
            "deidentification_confirmed",
        }:
            _fail()
        key = (_string(review["model_id"], 128), _string(review["sample_id"], 64))
        if key in reviews or key not in predictions:
            _fail()
        prediction = predictions[key]
        if (
            prediction["status"] != "SUCCESS"
            or prediction["scoring"]["word_errors"] + prediction["scoring"]["character_errors"] == 0
        ):
            _fail()
        reviewer_id = _string(review["reviewer_id"], 64)
        if reviewer_id in {
            prediction["reference_transcriber_id"],
            prediction["reference_reviewer_id"],
            prediction["recording_reviewer_id"],
        }:
            _fail()
        reviewed_at = _iso_date(review["reviewed_at"])
        if date.fromisoformat(reviewed_at) < date.fromisoformat(result["execution_date"]):
            _fail()
        if review["decision"] == "APPROVED":
            if (
                review["deidentification_confirmed"] is not True
                or prediction["error_example_permission"] is not True
            ):
                _fail()
            counts["approved"] += 1
        elif review["decision"] == "REJECTED":
            if review["deidentification_confirmed"] is not False:
                _fail()
            counts["rejected"] += 1
        else:
            _fail()
        reviews[key] = dict(review)
    error_count = len(
        {
            (model["model_id"], record["sample_id"])
            for model in result["model_results"].values()
            for record in model.get("records", [])
            if record["status"] == "SUCCESS"
            and record["scoring"]["word_errors"] + record["scoring"]["character_errors"] > 0
        }
    )
    counts["unreviewed"] = max(0, error_count - len(reviews))
    return reviews, counts


def public_report(
    result: dict[str, Any], review_document: Any | None = None
) -> tuple[dict[str, Any], str]:
    review_document = review_document or error_review_template(result["manifest_sha256"])
    approved_reviews, review_counts = validate_error_reviews(result, review_document)
    public_models: dict[str, Any] = {}
    approved_examples: list[dict[str, Any]] = []
    for key, model in result["model_results"].items():
        public_models[key] = {k: v for k, v in model.items() if k != "records"}
        for record in model.get("records", []):
            if (model["model_id"], record["sample_id"]) in approved_reviews and approved_reviews[
                (model["model_id"], record["sample_id"])
            ]["decision"] == "APPROVED":
                approved_examples.append(
                    {
                        "model_id": model["model_id"],
                        "language_group": record["language_group"],
                        "sample_id": record["sample_id"],
                        "reference_text": record["reference_text"],
                        "hypothesis_text": record["hypothesis_text"],
                        "word_errors": record["scoring"]["word_errors"],
                        "character_errors": record["scoring"]["character_errors"],
                    }
                )
    summary = {
        "schema_version": RESULT_SCHEMA,
        "protocol_id": result["protocol_id"],
        "label": "PILOT",
        "production_promotion": False,
        "v1_replacement": False,
        "manifest_sha256": result["manifest_sha256"],
        "protocol_sha256": result["protocol_sha256"],
        "normalization_version": result["normalization_version"],
        "execution_date": result["execution_date"],
        "error_review_registry_sha256": record_checksum(review_document),
        "error_example_review_counts": review_counts,
        "collection_counts": result["collection_counts"],
        "model_results": public_models,
        "strongest_model_by_language": result["strongest_model_by_language"],
        "approved_error_examples": approved_examples[:12],
        "limitations": result["limitations"],
    }
    lines = [
        "# VOICE-BASELINE-PILOT-V1 comparison",
        "",
        (
            "Status: **PILOT**. This report does not replace EVAL-VOICE-V1 or "
            "authorize production model selection."
        ),
        "",
        f"Frozen manifest SHA-256: `{result['manifest_sha256']}`",
        "",
        "## Collection counts",
        "",
        "| Language group | Selected recordings | Speakers | Native-attested speakers | Target |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for group, counts in result["collection_counts"].items():
        lines.append(
            f"| {group} | {counts['selected_recordings']} | {counts['speaker_count']} | "
            f"{counts['native_speaker_count']} | {TARGETS[group]} |"
        )
    lines.extend(
        [
            "",
            "## Results",
            "",
            "| Language group | Model | n | Speakers | WER | CER | Failure rate | "
            "Median latency (ms) |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for model in public_models.values():
        summary_row = model["summary"]
        if summary_row is None:
            lines.append(
                f"| {model['language_group']} | {model['model_id']} | — | — | — | — | — | — |"
            )
            continue
        latency = summary_row["latency_ms"]["median"] if summary_row["latency_ms"] else None

        def fmt(value: float | None) -> str:
            return "—" if value is None else f"{value:.4f}"

        lines.append(
            "| "
            + " | ".join(
                (
                    model["language_group"],
                    model["model_id"],
                    str(summary_row["sample_count"]),
                    str(summary_row["speaker_count"]),
                    fmt(summary_row["wer"]),
                    fmt(summary_row["cer"]),
                    fmt(summary_row["failed_transcription_rate"]),
                    fmt(latency),
                )
            )
            + " |"
        )
    lines.extend(["", "## Strongest measured model per language", ""])
    for group, entry in result["strongest_model_by_language"].items():
        winner = entry["model_id"] or (
            ", ".join(entry.get("tied_models", [])) if entry.get("tied_models") else "not available"
        )
        lines.append(f"- `{group}`: {winner} ({entry['status']}).")
    lines.extend(["", "## Error examples approved for this report", ""])
    if not summary["approved_error_examples"]:
        lines.append(
            "None included; no individually reviewed and consented example is currently releasable."
        )
    else:
        for example in summary["approved_error_examples"]:
            example_line = (
                f"- `{example['language_group']}` / `{example['model_id']}` / "
                f"`{example['sample_id']}`: reference "
                f"“{example['reference_text']}”; hypothesis "
                f"“{example['hypothesis_text']}”."
            )
            lines.append(example_line)
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in result["limitations"])
    return summary, "\n".join(lines) + "\n"


def initialize_workspace(root: Path, workspace: Path | None = None) -> dict[str, Any]:
    workspace = workspace or root / ".local/voice_baseline_pilot_v1"
    for directory in ("audio", "consent-evidence", "frozen", "runs"):
        (workspace / directory).mkdir(parents=True, exist_ok=True)
    input_path, consent_path = (
        workspace / "recordings_input.json",
        workspace / "consent_registry.json",
    )
    if not input_path.exists():
        put_json(
            input_path, {"schema_version": INPUT_SCHEMA, "source_id": SOURCE_ID, "recordings": []}
        )
    if not consent_path.exists():
        put_json(
            consent_path, {"schema_version": CONSENT_SCHEMA, "source_id": SOURCE_ID, "consents": []}
        )
    return {"workspace": str(workspace), "status": "PENDING_RECORDINGS"}


def status(root: Path, workspace: Path | None = None) -> dict[str, Any]:
    workspace = workspace or root / ".local/voice_baseline_pilot_v1"
    if (
        not (workspace / "recordings_input.json").exists()
        or not (workspace / "consent_registry.json").exists()
    ):
        initialize_workspace(root, workspace)
    input_doc = read_json(workspace / "recordings_input.json")
    consent_doc = read_json(workspace / "consent_registry.json")
    counts = {
        group: {
            "eligible_recordings": 0,
            "selected_recordings": 0,
            "speaker_count": 0,
            "native_speaker_count": 0,
            "target_recordings": TARGETS[group],
            "ideal_native_speakers": 5,
        }
        for group in LANGUAGE_GROUPS
    }
    try:
        checked = validate_bundle(
            input_doc,
            consent_doc,
            workspace / "audio",
            workspace / "consent-evidence",
        )
        for group in LANGUAGE_GROUPS:
            counts[group].update(checked["counts"][group])
    except (VoiceError, OSError):
        return {
            "protocol_id": PROTOCOL_ID,
            "label": "PILOT",
            "status": "INPUT_REQUIRES_REVIEW",
            "model_results": "NOT_RUN",
            "counts": counts,
        }
    return {
        "protocol_id": PROTOCOL_ID,
        "label": "PILOT",
        "status": checked["status"] if checked["eligible_recordings"] else "WAITING_FOR_RECORDINGS",
        "model_results": "NOT_RUN",
        "counts": counts,
    }
