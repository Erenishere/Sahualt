"""Independent human Sindhi holdout collection, validation, and freeze tooling."""

import hashlib
import re
from pathlib import Path
from typing import Any

from ..audio import read_audio
from ..benchmark.io import (
    file_sha256,
    put_immutable,
    put_json,
    read_canonical_json,
    read_json,
    record_checksum,
)
from ..errors import ErrorCode, VoiceError
from ..evaluation import resolve_audio_path

VERSION = "sindhi-holdout-v1-input"
DATASET = "SINDHI-HOLDOUT-V1"
UTTERANCE_FIELDS = {"utterance_id", "text", "domain", "length_category", "author", "reviewer"}
SPEAKER_FIELDS = {
    "speaker_id",
    "speaker_permission_confirmed",
    "speaker_public_corpus_attestation",
}
RECORDING_FIELDS = {
    "schema_version",
    "recording_id",
    "utterance_id",
    "speaker_id",
    "language",
    "domain",
    "audio_path",
    "audio_sha256",
    "reference_text",
    "reference_source",
    "reference_reviewer",
    "speaker_permission_confirmed",
    "speaker_public_corpus_attestation",
    "recording_source",
    "preparation_version",
}


def _id(value: object, prefix: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(rf"{prefix}[0-9]{{3}}", value):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    return value


def _text(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 512:
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    return value


def build_assignment(utterance_ids: list[str], speaker_ids: list[str]) -> list[dict[str, str]]:
    if len(utterance_ids) != 50 or len(speaker_ids) != 10:
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    if sorted(utterance_ids) != sorted(set(utterance_ids)) or sorted(speaker_ids) != sorted(
        set(speaker_ids)
    ):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    return [
        {
            "utterance_id": utterance_id,
            "speaker_ids": [speaker_ids[index % 10], speaker_ids[(index + 1) % 10]],
        }
        for index, utterance_id in enumerate(utterance_ids)
    ]


def validate(document: Any, audio_root: Path, *, require_complete: bool = False) -> dict[str, Any]:
    if (
        not isinstance(document, dict)
        or set(document) != {"schema_version", "utterances", "speakers", "recordings", "assignment"}
        or document["schema_version"] != VERSION
        or not isinstance(document["utterances"], list)
        or not isinstance(document["speakers"], list)
        or not isinstance(document["recordings"], list)
        or not isinstance(document["assignment"], list)
    ):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    utterances = {}
    for item in document["utterances"]:
        if not isinstance(item, dict) or set(item) != UTTERANCE_FIELDS:
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        uid = _id(item["utterance_id"], "UTT")
        if (
            uid in utterances
            or item["domain"] not in {"commerce", "everyday"}
            or item["length_category"] not in {"short", "medium", "long"}
        ):
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        _text(item["text"])
        if not all(
            isinstance(item[key], str) and item[key].strip() for key in ("author", "reviewer")
        ):
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        utterances[uid] = item
    speakers = {}
    for item in document["speakers"]:
        if not isinstance(item, dict) or set(item) != SPEAKER_FIELDS:
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        sid = _id(item["speaker_id"], "SPK")
        attestation = item["speaker_public_corpus_attestation"]
        if (
            sid in speakers
            or item["speaker_permission_confirmed"] is not True
            or not isinstance(attestation, dict)
        ):
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        if set(attestation) != {
            "common_voice",
            "fleurs",
            "buzzasr_related",
            "other_public_sindhi_asr",
        } or not all(isinstance(v, bool) for v in attestation.values()):
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        speakers[sid] = item
    records = []
    ids, hashes = set(), set()
    for item in document["recordings"]:
        if not isinstance(item, dict) or set(item) != RECORDING_FIELDS:
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        rid, uid, sid = (
            _id(item["recording_id"], "REC"),
            _id(item["utterance_id"], "UTT"),
            _id(item["speaker_id"], "SPK"),
        )
        if (
            rid in ids
            or uid not in utterances
            or sid not in speakers
            or item["language"] != "sd"
            or item["domain"] != utterances[uid]["domain"]
        ):
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        if (
            item["reference_text"] != utterances[uid]["text"]
            or item["reference_source"] != "human"
            or not isinstance(item["reference_reviewer"], str)
            or not item["reference_reviewer"].strip()
        ):
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        if (
            item["recording_source"] != "fresh_human_recording"
            or item["preparation_version"] != "sindhi-holdout-preparation-v1"
        ):
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        if (
            item["speaker_permission_confirmed"] is not True
            or item["speaker_public_corpus_attestation"]
            != speakers[sid]["speaker_public_corpus_attestation"]
        ):
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        if not isinstance(item["audio_path"], str) or not re.fullmatch(
            r"[A-Za-z0-9_./-]+\.wav", item["audio_path"]
        ):
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        if not isinstance(item["audio_sha256"], str) or not re.fullmatch(
            r"[0-9a-f]{64}", item["audio_sha256"]
        ):
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        if item["audio_sha256"] in hashes:
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        audio = read_audio(resolve_audio_path(audio_root, item["audio_path"]))
        if audio.sha256 != item["audio_sha256"]:
            raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
        ids.add(rid)
        hashes.add(audio.sha256)
        records.append(dict(item))
    assignment = document["assignment"]
    empty_pending = not utterances and not speakers and not records and not assignment
    if not empty_pending and assignment != build_assignment(sorted(utterances), sorted(speakers)):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    per_text = {uid: [] for uid in utterances}
    per_speaker = {sid: 0 for sid in speakers}
    for item in records:
        per_text[item["utterance_id"]].append(item["speaker_id"])
        per_speaker[item["speaker_id"]] += 1
    complete = (
        len(utterances) == 50
        and len(speakers) == 10
        and len(records) == 100
        and sum(i["domain"] == "commerce" for i in utterances.values()) == 30
        and sum(i["domain"] == "everyday" for i in utterances.values()) == 20
        and all(sorted(v) == sorted(set(v)) and len(v) == 2 for v in per_text.values())
        and all(v == 10 for v in per_speaker.values())
    )
    if require_complete and not complete:
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    return {
        "schema_version": VERSION,
        "utterances": sorted(utterances.values(), key=lambda x: x["utterance_id"]),
        "speakers": sorted(speakers.values(), key=lambda x: x["speaker_id"]),
        "recordings": sorted(records, key=lambda x: x["recording_id"]),
        "assignment": assignment,
        "complete": complete,
    }


def freeze(input_path: Path, audio_root: Path, output: Path, registry: Path) -> dict[str, Any]:
    document = validate(read_json(input_path), audio_root, require_complete=True)
    files = []
    for item in document["recordings"]:
        source = resolve_audio_path(audio_root, item["audio_path"])
        payload = source.read_bytes()
        if hashlib.sha256(payload).hexdigest() != item["audio_sha256"]:
            raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
        name = f"audio/{item['recording_id']}.wav"
        put_immutable(output / name, payload)
        item["audio_path"] = name
        files.append({"file": name, "sha256": item["audio_sha256"], "size": len(payload)})
    manifest = {
        "dataset_id": DATASET,
        "version": "sindhi-holdout-manifest-v1",
        "input": document,
        "sample_count": 100,
        "unique_utterance_count": 50,
        "speaker_count": 10,
        "buzzasr_training_overlap_known": False,
        "independence_statement": (
            "Audio recordings were newly collected and were not sourced from FLEURS "
            "or Common Voice 25; phrase-level text-only overlap is not claimed absent."
        ),
        "files": files,
        "semantic_sha256": record_checksum(document),
    }
    put_json(output / "manifest.json", manifest)
    put_json(
        registry, {"dataset_id": DATASET, "manifest_sha256": file_sha256(output / "manifest.json")}
    )
    return verify(output, registry)


def verify(output: Path, registry: Path) -> dict[str, Any]:
    manifest = read_canonical_json(output / "manifest.json")
    if (
        read_canonical_json(registry)
        != {"dataset_id": DATASET, "manifest_sha256": file_sha256(output / "manifest.json")}
        or manifest["dataset_id"] != DATASET
    ):
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    result = validate(manifest["input"], output, require_complete=True)
    if (
        result != manifest["input"]
        or manifest["sample_count"] != 100
        or manifest["unique_utterance_count"] != 50
        or manifest["speaker_count"] != 10
        or manifest["buzzasr_training_overlap_known"] is not False
    ):
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    return {
        "dataset_id": DATASET,
        "status": "FROZEN_VERIFIED",
        "sample_count": 100,
        "unique_utterance_count": 50,
        "speaker_count": 10,
        "manifest_sha256": file_sha256(output / "manifest.json"),
    }
