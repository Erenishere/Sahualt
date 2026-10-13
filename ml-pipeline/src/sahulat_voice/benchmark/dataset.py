import hashlib
import re
import tarfile
from pathlib import Path, PurePosixPath
from typing import Any, cast

from ..errors import ErrorCode, VoiceError
from ..evaluation import EVALUATION_SCHEMA, load_evaluation_input
from ..transcript import canonical_bytes
from .audio import MAX_SOURCE_WAV_BYTES, PreparedAudio, prepare_wav
from .io import file_sha256, put_immutable, put_json, read_canonical_json, record_checksum
from .metadata import FleursRow, read_metadata, select_rows
from .protocol import (
    ARTIFACT_PATH,
    CORPUS_PATH,
    DATASET_ID,
    LANGUAGE_CONFIGS,
    PROTOCOL_ID,
    protocol_inputs,
    runtime_identity,
    scoring_text,
    verify_protocol,
)
from .source import asset_from_record, validate_cached

ATTRIBUTION = (
    b"# FLEURS-VOICE-V1 attribution\n\n"
    b"Source: Google FLEURS, Conneau et al. (2022),\n"
    b"FLEURS: Few-shot Learning Evaluation of Universal Representations of Speech.\n"
    b"https://arxiv.org/abs/2205.12446\n"
    b"https://huggingface.co/datasets/google/fleurs\n\n"
    b"License: Creative Commons Attribution 4.0 International (CC BY 4.0).\n"
    b"https://creativecommons.org/licenses/by/4.0/\n\n"
    b"Changes: deterministic test subset selection and offline PCM16 WAV preparation.\n"
    b"No resampling, trimming, denoising, translation or generated reference text.\n"
    b"Original selected WAVs, source TSVs and exact published reference scripts are retained.\n"
    b"No endorsement by Google or the dataset authors is implied.\n"
)


def _read_selected(
    archive_path: Path, selected: list[FleursRow]
) -> dict[str, tuple[bytes, str, PreparedAudio]]:
    wanted = {row.filename: row for row in selected}
    found: dict[str, tuple[bytes, str, PreparedAudio]] = {}
    expanded, members = 0, 0
    try:
        with tarfile.open(archive_path, mode="r|gz") as archive:
            for member in archive:
                members += 1
                expanded += member.size
                relative = PurePosixPath(member.name)
                if (
                    member.size < 0
                    or expanded > 4 * 1024**3
                    or members > 20000
                    or relative.is_absolute()
                    or ".." in relative.parts
                    or "\\" in member.name
                    or ":" in member.name
                    or not (member.isfile() or member.isdir())
                ):
                    raise VoiceError(ErrorCode.INVALID_MANIFEST)
                filename = relative.name
                if filename not in wanted:
                    continue
                if (
                    not member.isfile()
                    or relative.as_posix() != f"test/{filename}"
                    or filename in found
                    or member.size > MAX_SOURCE_WAV_BYTES
                ):
                    raise VoiceError(ErrorCode.INVALID_MANIFEST)
                stream = archive.extractfile(member)
                if stream is None:
                    raise VoiceError(ErrorCode.INVALID_MANIFEST)
                with stream:
                    payload = stream.read(MAX_SOURCE_WAV_BYTES + 1)
                if len(payload) != member.size:
                    raise VoiceError(ErrorCode.INVALID_AUDIO)
                found[filename] = (
                    payload,
                    relative.as_posix(),
                    prepare_wav(payload, wanted[filename].frames),
                )
    except (tarfile.TarError, EOFError):
        raise VoiceError(ErrorCode.INVALID_MANIFEST) from None
    if set(found) != set(wanted):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    return found


def _metadata_selection(
    payload: bytes, config: str, expected_rows: int
) -> tuple[list[FleursRow], dict[str, object]]:
    rows, malformed = read_metadata(payload)
    if len(rows) + len(malformed) != expected_rows:
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    # A score-normalized empty reference cannot be a meaningful ASR reference.
    eligible = [row for row in rows if scoring_text(row.raw_transcription)]
    unusable = [
        {
            "filename": row.filename,
            "source_row": row.source_row,
            "reason": "empty-scoring-reference",
        }
        for row in rows
        if row not in eligible
    ]
    selected, excluded = select_rows(eligible, config)
    all_excluded = sorted(
        malformed + unusable + excluded, key=lambda record: cast(int, record["source_row"])
    )
    return selected, {
        "source_rows": expected_rows,
        "eligible_recordings": len(eligible),
        "eligible_sentence_ids": len({row.sentence_id for row in eligible}),
        "selected_recordings": len(selected),
        "selected_sentence_ids": len({row.sentence_id for row in selected}),
        "excluded_recordings": len(all_excluded),
        "exclusions": all_excluded,
    }


def _semantic_checksum(records: list[dict[str, Any]]) -> str:
    semantic = [
        {key: row[key] for key in ("sample_id", "language", "audio_sha256", "reference_text")}
        for row in sorted(records, key=lambda row: row["sample_id"])
    ]
    return record_checksum({"dataset_id": DATASET_ID, "samples": semantic})


def prepare_subset(root: Path, source_root: Path) -> dict[str, Any]:
    registry = verify_protocol(root)
    _, source = protocol_inputs(root)
    runtime = runtime_identity()
    target = root / ARTIFACT_PATH
    payloads: dict[str, bytes] = {"ATTRIBUTION.md": ATTRIBUTION}
    samples: list[dict[str, Any]] = []
    lineage: list[dict[str, Any]] = []
    audits: dict[str, object] = {}
    card = validate_cached(source_root, asset_from_record(source["card"]))
    payloads["source_metadata/README.md"] = card.read_bytes()
    for language, config in LANGUAGE_CONFIGS.items():
        specification = source["languages"][language]
        metadata = validate_cached(source_root, asset_from_record(specification["metadata"]))
        archive = validate_cached(source_root, asset_from_record(specification["archive"]))
        raw_metadata = metadata.read_bytes()
        payloads[f"source_metadata/{config}/test.tsv"] = raw_metadata
        selected, audit = _metadata_selection(raw_metadata, config, specification["rows"])
        audits[language] = audit
        extracted = _read_selected(archive, selected)
        for row in selected:
            original, member, prepared = extracted[row.filename]
            sample_id = f"fleurs_{config}_{row.filename[:-4]}"
            audio_path = f"audio/{language}/{row.filename}"
            original_path = f"source_audio/{language}/{row.filename}"
            payloads[audio_path], payloads[original_path] = prepared.wav, original
            samples.append(
                {
                    "sample_id": sample_id,
                    "language": language,
                    "audio_path": audio_path,
                    "audio_sha256": prepared.sha256,
                    "reference_text": row.raw_transcription,
                    "reference_author": "dataset:google/fleurs-published-reference",
                    "reference_source": "human",
                    "source": "licensed_dataset",
                    "use_permission_confirmed": True,
                }
            )
            lineage.append(
                {
                    "sample_id": sample_id,
                    "config": config,
                    "split": "test",
                    "sentence_id": row.sentence_id,
                    "source_row": row.source_row,
                    "filename": row.filename,
                    "archive_member": member,
                    "original_audio_path": original_path,
                    "raw_transcription": row.raw_transcription,
                    "published_transcription": row.transcription,
                    "audio": prepared.evidence(),
                }
            )
    ordered_samples = sorted(samples, key=lambda row: row["sample_id"])
    ordered_lineage = sorted(lineage, key=lambda row: row["sample_id"])
    payloads["evaluation-input.json"] = canonical_bytes(
        {"schema_version": EVALUATION_SCHEMA, "samples": ordered_samples}
    )
    payloads["lineage.json"] = canonical_bytes(
        {
            "version": "fleurs-lineage-v1",
            "samples": ordered_lineage,
        }
    )
    payloads["metadata-audit.json"] = canonical_bytes(
        {"version": "fleurs-metadata-audit-v1", "languages": audits}
    )
    # All four languages are completely built before any derived files are installed.
    for relative, payload in sorted(payloads.items()):
        put_immutable(target / relative, payload)
    load_evaluation_input(target / "evaluation-input.json", target)
    manifest: dict[str, Any] = {
        "manifest_version": "voice-dataset-manifest-v1",
        "dataset_id": DATASET_ID,
        "state": "PREPARED_REQUIRES_EXTERNAL_FREEZE",
        "protocol_id": PROTOCOL_ID,
        "protocol_registry_checksum": registry["registry_checksum"],
        "source_revision": source["revision"],
        "source_license": source["license"],
        "source_lock_sha256": record_checksum(source),
        "runtime": runtime,
        "sample_count": len(samples),
        "language_counts": {language: 50 for language in LANGUAGE_CONFIGS},
        "semantic_sha256": _semantic_checksum(samples),
        "model_results": "NOT_RUN",
        "files": {
            path: hashlib.sha256(payload).hexdigest() for path, payload in sorted(payloads.items())
        },
    }
    put_json(target / "manifest.json", manifest)
    verify_prepared(root)
    return manifest


def _safe_bundle_file(target: Path, relative: str) -> Path:
    posix = PurePosixPath(relative)
    if (
        posix.is_absolute()
        or ".." in posix.parts
        or "\\" in relative
        or ":" in relative
        or posix.as_posix() != relative
    ):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    resolved = (target / relative).resolve()
    if not resolved.is_relative_to(target.resolve()):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    return resolved


def verify_prepared(root: Path) -> dict[str, Any]:
    registry = verify_protocol(root)
    _, source = protocol_inputs(root)
    target = root / ARTIFACT_PATH
    manifest = read_canonical_json(target / "manifest.json")
    if (
        not isinstance(manifest, dict)
        or set(manifest)
        != {
            "manifest_version",
            "dataset_id",
            "state",
            "protocol_id",
            "protocol_registry_checksum",
            "source_revision",
            "source_license",
            "source_lock_sha256",
            "runtime",
            "sample_count",
            "language_counts",
            "semantic_sha256",
            "model_results",
            "files",
        }
        or manifest.get("state") != "PREPARED_REQUIRES_EXTERNAL_FREEZE"
        or manifest.get("dataset_id") != DATASET_ID
        or manifest.get("manifest_version") != "voice-dataset-manifest-v1"
        or manifest.get("protocol_id") != PROTOCOL_ID
        or manifest.get("protocol_registry_checksum") != registry["registry_checksum"]
        or manifest.get("source_lock_sha256") != record_checksum(source)
        or manifest.get("source_revision") != source["revision"]
        or manifest.get("source_license") != "cc-by-4.0"
        or manifest.get("sample_count") != 200
        or manifest.get("language_counts") != {language: 50 for language in LANGUAGE_CONFIGS}
        or manifest.get("runtime") != runtime_identity()
        or manifest.get("model_results") != "NOT_RUN"
        or not isinstance(manifest.get("files"), dict)
    ):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    for relative, checksum in manifest["files"].items():
        if (
            not isinstance(relative, str)
            or not isinstance(checksum, str)
            or not re.fullmatch(r"[0-9a-f]{64}", checksum)
            or file_sha256(_safe_bundle_file(target, relative)) != checksum
        ):
            raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    document = read_canonical_json(target / "evaluation-input.json")
    lineage = read_canonical_json(target / "lineage.json")
    audits = read_canonical_json(target / "metadata-audit.json")
    load_evaluation_input(target / "evaluation-input.json", target)
    if (
        not isinstance(lineage, dict)
        or set(lineage) != {"version", "samples"}
        or lineage.get("version") != "fleurs-lineage-v1"
        or not isinstance(lineage.get("samples"), list)
        or len(lineage["samples"]) != 200
        or not isinstance(audits, dict)
        or set(audits) != {"version", "languages"}
        or not isinstance(audits.get("languages"), dict)
        or set(audits["languages"]) != set(LANGUAGE_CONFIGS)
        or audits.get("version") != "fleurs-metadata-audit-v1"
    ):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    lineage_keys = {
        "sample_id",
        "config",
        "split",
        "sentence_id",
        "source_row",
        "filename",
        "archive_member",
        "original_audio_path",
        "raw_transcription",
        "published_transcription",
        "audio",
    }
    if any(
        not isinstance(row, dict)
        or set(row) != lineage_keys
        or not isinstance(row.get("sample_id"), str)
        for row in lineage["samples"]
    ):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    expected_samples: list[dict[str, Any]] = []
    expected_paths = {
        "ATTRIBUTION.md",
        "source_metadata/README.md",
        "evaluation-input.json",
        "lineage.json",
        "metadata-audit.json",
    }
    if (
        file_sha256(target / "source_metadata/README.md") != source["card"]["sha256"]
        or (target / "ATTRIBUTION.md").read_bytes() != ATTRIBUTION
    ):
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    lineage_by_id = {row["sample_id"]: row for row in lineage["samples"]}
    if len(lineage_by_id) != 200:
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    for language, config in LANGUAGE_CONFIGS.items():
        metadata_path = f"source_metadata/{config}/test.tsv"
        expected_paths.add(metadata_path)
        spec = source["languages"][language]
        if file_sha256(target / metadata_path) != spec["metadata"]["sha256"]:
            raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
        selected, audit = _metadata_selection(
            (target / metadata_path).read_bytes(), config, spec["rows"]
        )
        if audits.get("languages", {}).get(language) != audit:
            raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
        for row in selected:
            sample_id = f"fleurs_{config}_{row.filename[:-4]}"
            trace = lineage_by_id.get(sample_id)
            audio_path, original_path = (
                f"audio/{language}/{row.filename}",
                f"source_audio/{language}/{row.filename}",
            )
            expected_paths.update((audio_path, original_path))
            with _safe_bundle_file(target, original_path).open("rb") as stream:
                original = stream.read(MAX_SOURCE_WAV_BYTES + 1)
            prepared = prepare_wav(original, row.frames)
            if (
                not isinstance(trace, dict)
                or trace.get("config") != config
                or trace.get("split") != "test"
                or trace.get("sentence_id") != row.sentence_id
                or trace.get("source_row") != row.source_row
                or trace.get("filename") != row.filename
                or trace.get("archive_member") != f"test/{row.filename}"
                or trace.get("original_audio_path") != original_path
                or trace.get("raw_transcription") != row.raw_transcription
                or trace.get("published_transcription") != row.transcription
                or trace.get("audio") != prepared.evidence()
                or (target / audio_path).read_bytes() != prepared.wav
            ):
                raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
            expected_samples.append(
                {
                    "sample_id": sample_id,
                    "language": language,
                    "audio_path": audio_path,
                    "audio_sha256": prepared.sha256,
                    "reference_text": row.raw_transcription,
                    "reference_author": "dataset:google/fleurs-published-reference",
                    "reference_source": "human",
                    "source": "licensed_dataset",
                    "use_permission_confirmed": True,
                }
            )
    expected_document = {
        "schema_version": EVALUATION_SCHEMA,
        "samples": sorted(expected_samples, key=lambda row: row["sample_id"]),
    }
    if (
        document != expected_document
        or set(manifest["files"]) != expected_paths
        or {path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_file()}
        != expected_paths | {"manifest.json"}
        or manifest.get("semantic_sha256") != _semantic_checksum(expected_samples)
    ):
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    return manifest


def _corpus_descriptor(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "registry_version": "fleurs-voice-corpus-v1",
        "dataset_id": DATASET_ID,
        "status": "FROZEN",
        "protocol_id": PROTOCOL_ID,
        "artifact_root": ARTIFACT_PATH,
        "sample_count": 200,
        "language_counts": manifest["language_counts"],
        "source_revision": manifest["source_revision"],
        "source_lock_sha256": manifest["source_lock_sha256"],
        "protocol_registry_checksum": manifest["protocol_registry_checksum"],
        "manifest_sha256": file_sha256(root / ARTIFACT_PATH / "manifest.json"),
        "semantic_sha256": manifest["semantic_sha256"],
        "model_results": "NOT_RUN",
    }


def freeze_subset(root: Path) -> dict[str, Any]:
    manifest = verify_prepared(root)
    put_json(root / CORPUS_PATH, _corpus_descriptor(root, manifest))
    return verify_frozen(root)


def verify_frozen(root: Path) -> dict[str, Any]:
    manifest = verify_prepared(root)
    actual = read_canonical_json(root / CORPUS_PATH)
    expected = _corpus_descriptor(root, manifest)
    if actual != expected:
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    return expected
