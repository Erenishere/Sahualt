import re
from datetime import datetime
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
from ..contracts import NORMALIZATION_VERSION
from ..errors import ErrorCode, VoiceError
from ..evaluation import resolve_audio_path
from ..runs.scoring import score
from ..transcript import normalize_transcript

VERSION = "sindhi-holdout-input-v1"
DATASET = "SINDHI-HOLDOUT-V1"
FIELDS = {
    "recording_id",
    "speaker_pseudonym",
    "audio_path",
    "audio_sha256",
    "original_audio_sha256",
    "reference_text",
    "reference_author",
    "reference_provenance",
    "recorded_at",
    "consent_confirmed",
    "use_permission_confirmed",
    "language",
    "source",
    "fresh_human_recording_confirmed",
    "not_used_for_model_training_confirmed",
}


def identifier(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", value):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    return value


def validate(document: Any, audio_root: Path) -> dict[str, Any]:
    if (
        not isinstance(document, dict)
        or set(document) != {"schema_version", "excluded_speaker_ids", "samples"}
        or document["schema_version"] != VERSION
        or not isinstance(document["samples"], list)
        or len(document["samples"]) > 200
        or not isinstance(document["excluded_speaker_ids"], list)
    ):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    excluded = [identifier(value) for value in document["excluded_speaker_ids"]]
    if len(excluded) != len(set(excluded)):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    ids: set[str] = set()
    audios: set[str] = set()
    records = []
    for record in document["samples"]:
        if not isinstance(record, dict) or set(record) != FIELDS:
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        rid, speaker = identifier(record["recording_id"]), identifier(record["speaker_pseudonym"])
        if rid in ids or speaker in excluded:
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        for key in ("reference_text", "reference_author", "reference_provenance"):
            value = record[key]
            if not isinstance(value, str) or not normalize_transcript(value):
                raise VoiceError(ErrorCode.INVALID_MANIFEST)
        try:
            date = record["recorded_at"]
            if not isinstance(date, str) or not date.endswith("Z"):
                raise ValueError
            datetime.fromisoformat(date[:-1] + "+00:00")
        except (TypeError, ValueError):
            raise VoiceError(ErrorCode.INVALID_MANIFEST) from None
        if (
            record["language"] != "sd"
            or record["source"] != "human_recording"
            or any(
                record[key] is not True
                for key in (
                    "consent_confirmed",
                    "use_permission_confirmed",
                    "fresh_human_recording_confirmed",
                    "not_used_for_model_training_confirmed",
                )
            )
            or not isinstance(record["audio_path"], str)
            or not isinstance(record["audio_sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", record["audio_sha256"])
            or record["original_audio_sha256"] != record["audio_sha256"]
            or record["audio_sha256"] in audios
        ):
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        audio = read_audio(resolve_audio_path(audio_root, record["audio_path"]))
        if audio.sha256 != record["audio_sha256"]:
            raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
        # Check frozen scoring eligibility, preserving the exact original human reference.
        score(record["reference_text"], "")
        ids.add(rid)
        audios.add(audio.sha256)
        records.append(dict(record))
    return {
        "schema_version": VERSION,
        "excluded_speaker_ids": sorted(excluded),
        "samples": sorted(records, key=lambda r: r["recording_id"]),
    }


def freeze(input_path: Path, audio_root: Path, output: Path, registry: Path) -> dict[str, Any]:
    document = validate(read_json(input_path), audio_root)
    if not document["samples"]:
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    files = []
    prepared = []
    for record in document["samples"]:
        source = resolve_audio_path(audio_root, record["audio_path"])
        payload = source.read_bytes()
        import hashlib

        if hashlib.sha256(payload).hexdigest() != record["audio_sha256"]:
            raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
        name = f"audio/{record['recording_id']}.wav"
        prepared.append((name, payload))
        files.append({"file": name, "sha256": record["audio_sha256"], "size": len(payload)})
        record["audio_path"] = name
    manifest = {
        "dataset_id": DATASET,
        "version": "sindhi-holdout-manifest-v1",
        "normalization_version": NORMALIZATION_VERSION,
        "input": document,
        "sample_count": len(document["samples"]),
        "speaker_ids": sorted({r["speaker_pseudonym"] for r in document["samples"]}),
        "human_provenance": "DECLARED;NOT_AUTOMATICALLY_VERIFIED",
        "model_selection_evaluation": "REQUIRES_SEPARATE_APPROVED_PROTOCOL",
        "semantic_sha256": record_checksum(document),
        "files": files,
    }
    anchor = {"dataset_id": DATASET, "manifest_sha256": record_checksum(manifest)}
    # Validate any existing anchors before writing; never reconcile a changed frozen dataset.
    if registry.exists() and read_canonical_json(registry) != anchor:
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    if (output / "manifest.json").exists() and read_canonical_json(
        output / "manifest.json"
    ) != manifest:
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    for name, payload in prepared:
        put_immutable(output / name, payload)
    put_json(output / "manifest.json", manifest)
    put_json(registry, anchor)
    return verify(output, registry)


def verify(output: Path, registry: Path) -> dict[str, Any]:
    manifest_path = output / "manifest.json"
    manifest = read_canonical_json(manifest_path)
    if read_canonical_json(registry) != {
        "dataset_id": DATASET,
        "manifest_sha256": file_sha256(manifest_path),
    }:
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    document = validate(manifest["input"], output)
    if (
        not document["samples"]
        or document != manifest["input"]
        or manifest["dataset_id"] != DATASET
        or manifest["version"] != "sindhi-holdout-manifest-v1"
        or manifest["normalization_version"] != NORMALIZATION_VERSION
        or manifest["sample_count"] != len(document["samples"])
        or manifest["semantic_sha256"] != record_checksum(document)
        or manifest["speaker_ids"] != sorted({r["speaker_pseudonym"] for r in document["samples"]})
    ):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    expected = [
        {
            "file": r["audio_path"],
            "sha256": r["audio_sha256"],
            "size": (output / r["audio_path"]).stat().st_size,
        }
        for r in document["samples"]
    ]
    actual_files = {p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()}
    if manifest["files"] != expected or actual_files != {
        "manifest.json",
        *(r["file"] for r in expected),
    }:
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    return {
        "dataset_id": DATASET,
        "status": "FROZEN_VERIFIED",
        "sample_count": len(document["samples"]),
        "manifest_sha256": file_sha256(manifest_path),
        "selection_evaluation": "NOT_AUTHORIZED",
    }
