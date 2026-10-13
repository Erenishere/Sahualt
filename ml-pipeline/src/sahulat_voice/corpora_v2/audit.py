import hashlib
import json
import math
import re
import urllib.parse
import urllib.request
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any

from ..benchmark.io import (
    file_sha256,
    put_immutable,
    put_json,
    read_canonical_json,
    record_checksum,
)
from ..errors import ErrorCode, VoiceError
from .registry import (
    AUDIT_GATE_PATH,
    AUDIT_JSON_PATH,
    AUDIT_MARKDOWN_PATH,
    CONFIG_PATH,
    PROTOCOL_ID,
    load_registry,
    verify_protocol,
)

MAX_API_BYTES = 32 * 1024 * 1024
MAX_METADATA_BYTES = 2 * 1024 * 1024
MAX_METADATA_LINES = 10000
Fetch = Callable[[str, int], bytes]


def fetch_url(url: str, limit: int) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"Accept-Encoding": "identity", "User-Agent": "Sahulat-VOICE-CORPORA-V2"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read(limit + 1)
    except Exception:
        raise VoiceError(ErrorCode.IO_FAILED) from None
    if len(payload) > limit:
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    return payload


def _json_bytes(payload: bytes) -> Any:
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise VoiceError(ErrorCode.INVALID_MANIFEST)
            result[key] = value
        return result

    try:
        return json.loads(payload.decode("utf-8"), object_pairs_hook=unique)
    except VoiceError:
        raise
    except (ValueError, UnicodeError, RecursionError):
        raise VoiceError(ErrorCode.INVALID_MANIFEST) from None


def _git_blob_id(payload: bytes) -> str:
    return hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()


def parse_inventory(payload: bytes, benchmark_root: str) -> list[dict[str, Any]]:
    document = _json_bytes(payload)
    if not isinstance(document, dict) or not isinstance(document.get("siblings"), list):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    records: list[dict[str, Any]] = []
    paths: set[str] = set()
    prefix = benchmark_root + "/"
    for item in document["siblings"]:
        if not isinstance(item, dict) or not isinstance(item.get("rfilename"), str):
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        path = item["rfilename"]
        if not path.startswith(prefix):
            continue
        relative = PurePosixPath(path)
        size = item.get("size")
        blob_id = item.get("blobId")
        lfs = item.get("lfs")
        if (
            path in paths
            or relative.is_absolute()
            or ".." in relative.parts
            or "\\" in path
            or relative.as_posix() != path
            or type(size) is not int
            or not 0 < size <= 64 * 1024 * 1024
            or not isinstance(blob_id, str)
            or re.fullmatch(r"[0-9a-f]{40}", blob_id) is None
        ):
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        paths.add(path)
        record: dict[str, Any] = {"path": path, "size": size, "blob_id": blob_id}
        if lfs is not None:
            if (
                not isinstance(lfs, dict)
                or re.fullmatch(r"[0-9a-f]{64}", str(lfs.get("sha256"))) is None
                or lfs.get("size") != size
            ):
                raise VoiceError(ErrorCode.INVALID_MANIFEST)
            record["lfs_sha256"] = lfs["sha256"]
        records.append(record)
    return sorted(records, key=lambda item: item["path"])


def inventory_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    audio = [record for record in records if "/audio/" in record["path"]]
    metadata = [record for record in records if "/audio/" not in record["path"]]
    if any("lfs_sha256" not in record for record in audio) or any(
        "lfs_sha256" in record for record in metadata
    ):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    stable = [
        {
            "path": record["path"],
            "size": record["size"],
            "blob_id": record["blob_id"],
            **({"lfs_sha256": record["lfs_sha256"]} if "lfs_sha256" in record else {}),
        }
        for record in records
    ]
    return {
        "file_count": len(records),
        "byte_count": sum(record["size"] for record in records),
        "audio_file_count": len(audio),
        "metadata_file_count": len(metadata),
        "metadata_byte_count": sum(record["size"] for record in metadata),
        "inventory_sha256": record_checksum(stable),
    }


def _positive_duration(value: object) -> float:
    if isinstance(value, bool):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    if isinstance(value, (int, float)):
        parsed = float(value)
    elif isinstance(value, str) and re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value):
        parsed = float(value)
    else:
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    if math.isfinite(parsed) and 0 < parsed <= 3600:
        return parsed
    raise VoiceError(ErrorCode.INVALID_MANIFEST)


def parse_clean_metadata(
    payload: bytes,
    metadata_path: str,
    subset: str,
    audio_assets: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    if len(payload) > MAX_METADATA_BYTES:
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    expected_fields = {
        "Speaker_id",
        "Audio_category",
        "Audio_Clip",
        "audio_id",
        "Duration_seconds",
        "Word_count",
        "Character_count",
        "Transcription",
        "ground_truth",
    }
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeError:
        raise VoiceError(ErrorCode.INVALID_MANIFEST) from None
    if not 0 < len(lines) <= MAX_METADATA_LINES:
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    parent = PurePosixPath(metadata_path).parent
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in lines:
        item = _json_bytes(line.encode("utf-8"))
        if not isinstance(item, dict) or set(item) != expected_fields:
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        speaker = item["Speaker_id"]
        category = item["Audio_category"]
        clip = item["Audio_Clip"]
        reference = item["ground_truth"]
        if (
            not isinstance(speaker, str)
            or re.fullmatch(r"SPEAKER_[0-9]+", speaker) is None
            or not isinstance(category, str)
            or re.fullmatch(r"[A-Za-z0-9_-]+", category) is None
            or not isinstance(clip, str)
            or PurePosixPath(clip).name != clip
            or re.fullmatch(r"[A-Za-z0-9_.-]+\.[Ww][Aa][Vv]", clip) is None
            or not isinstance(item["audio_id"], str)
            or not isinstance(reference, str)
            or not reference.strip()
            or not isinstance(item["Transcription"], str)
        ):
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        audio_path = (parent / "audio" / clip).as_posix()
        if audio_path in seen or audio_path not in audio_assets:
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        seen.add(audio_path)
        duration = _positive_duration(item["Duration_seconds"])
        asset = audio_assets[audio_path]
        sample_digest = hashlib.sha256(audio_path.encode()).hexdigest()[:16]
        records.append(
            {
                "sample_id": f"urduspeech_{subset}_{sample_digest}",
                "subset": subset,
                "speaker_id": speaker,
                "category": category,
                "duration_group": "long" if "/long/" in metadata_path else "short",
                "duration_seconds": duration,
                "audio_path": audio_path,
                "audio_size": asset["size"],
                "audio_sha256": asset["lfs_sha256"],
                "reference_sha256": hashlib.sha256(reference.encode("utf-8")).hexdigest(),
                "published_transcription_matches_ground_truth": item["Transcription"] == reference,
            }
        )
    return records


def _selection_key(seed: int, subset: str, value: str) -> str:
    return hashlib.sha256(f"{PROTOCOL_ID}|{seed}|{subset}|{value}".encode()).hexdigest()


def selection_preview(
    records: list[dict[str, Any]], subset: str, target: int, seed: int
) -> dict[str, Any]:
    hash_counts: dict[str, int] = defaultdict(int)
    for record in records:
        hash_counts[record["audio_sha256"]] += 1
    duplicate_hashes = {digest for digest, count in hash_counts.items() if count > 1}
    eligible = [
        record
        for record in records
        if record["duration_seconds"] <= 30 and record["audio_sha256"] not in duplicate_hashes
    ]
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in eligible:
        groups[(record["duration_group"], record["category"], record["speaker_id"])].append(record)
    for values in groups.values():
        values.sort(key=lambda item: _selection_key(seed, subset, item["sample_id"]))
    group_keys = sorted(
        groups,
        key=lambda key: _selection_key(seed, subset, "|".join(key)),
    )
    selected: list[dict[str, Any]] = []
    while len(selected) < min(target, len(eligible)):
        progressed = False
        for key in group_keys:
            if groups[key] and len(selected) < target:
                selected.append(groups[key].pop(0))
                progressed = True
        if not progressed:
            break
    selected.sort(key=lambda item: item["sample_id"])
    return {
        "source_record_count": len(records),
        "runtime_duration_eligible_count": sum(
            record["duration_seconds"] <= 30 for record in records
        ),
        "duplicate_audio_excluded_count": sum(
            record["audio_sha256"] in duplicate_hashes for record in records
        ),
        "target": target,
        "selected_count": len(selected),
        "target_met": len(selected) == target,
        "selection_status": "PREVIEW_NOT_FROZEN",
        "records": selected,
    }


def _subset_key(path: str, subsets: dict[str, Any]) -> str:
    matches = [key for key, record in subsets.items() if path.startswith(record["path"] + "/")]
    if len(matches) != 1:
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    return matches[0]


def build_audit(root: Path, fetch: Fetch = fetch_url) -> dict[str, Any]:
    protocol_gate = verify_protocol(root)
    registry = load_registry(root)
    urdu = registry["sources"]["urduspeech"]
    revision = urdu["revision"]
    repository = urdu["repository"]
    api_url = f"https://huggingface.co/api/datasets/{repository}/revision/{revision}?blobs=true"
    api_payload = fetch(api_url, MAX_API_BYTES)
    api_document = _json_bytes(api_payload)
    if (
        not isinstance(api_document, dict)
        or api_document.get("id") != repository
        or api_document.get("sha") != revision
        or api_document.get("private") is not False
        or api_document.get("gated") not in (False, "auto", "manual")
    ):
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    inventory = parse_inventory(api_payload, urdu["benchmark_root"])
    summary = inventory_summary(inventory)
    if summary != urdu["expected_inventory"]:
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)

    subsets = urdu["subsets"]
    subset_inventory: dict[str, dict[str, int]] = {}
    for key, contract in subsets.items():
        files = [item for item in inventory if item["path"].startswith(contract["path"] + "/")]
        subset_inventory[key] = {
            "file_count": len(files),
            "byte_count": sum(item["size"] for item in files),
            "audio_file_count": sum("/audio/" in item["path"] for item in files),
            "metadata_file_count": sum("/audio/" not in item["path"] for item in files),
        }
        if (
            subset_inventory[key]["file_count"] != contract["expected_file_count"]
            or subset_inventory[key]["byte_count"] != contract["expected_byte_count"]
        ):
            raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)

    audio_assets = {item["path"]: item for item in inventory if "/audio/" in item["path"]}
    metadata_assets = {
        item["path"]: item
        for item in inventory
        if item["path"].endswith("/clean_transcription.jsonl")
    }
    if len(metadata_assets) * 2 != summary["metadata_file_count"]:
        raise VoiceError(ErrorCode.INVALID_MANIFEST)

    records_by_subset: dict[str, list[dict[str, Any]]] = {key: [] for key in subsets}
    metadata_evidence: list[dict[str, Any]] = []
    for path, asset in sorted(metadata_assets.items()):
        quoted_path = urllib.parse.quote(path, safe="/")
        url = f"https://huggingface.co/datasets/{repository}/resolve/{revision}/{quoted_path}"
        payload = fetch(url, MAX_METADATA_BYTES)
        if len(payload) != asset["size"] or _git_blob_id(payload) != asset["blob_id"]:
            raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
        subset = _subset_key(path, subsets)
        parsed = parse_clean_metadata(payload, path, subset, audio_assets)
        records_by_subset[subset].extend(parsed)
        metadata_evidence.append(
            {
                "path": path,
                "size": len(payload),
                "git_blob_id": asset["blob_id"],
                "sha256": hashlib.sha256(payload).hexdigest(),
                "row_count": len(parsed),
            }
        )

    all_records = [record for records in records_by_subset.values() for record in records]
    if len(all_records) != len(audio_assets) or len(
        {item["audio_path"] for item in all_records}
    ) != len(all_records):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    audio_hashes: dict[str, list[str]] = defaultdict(list)
    for record in all_records:
        audio_hashes[record["audio_sha256"]].append(record["audio_path"])
    duplicate_groups = [sorted(paths) for paths in audio_hashes.values() if len(paths) > 1]

    speaker_subsets: dict[str, set[str]] = defaultdict(set)
    for record in all_records:
        speaker_subsets[record["speaker_id"]].add(record["subset"])
    repeated_identifiers = sorted(
        identifier for identifier, values in speaker_subsets.items() if len(values) > 1
    )

    selections = {
        key: selection_preview(
            records_by_subset[key],
            key,
            contract["sample_target"],
            registry["protocol"]["selection_seed"],
        )
        for key, contract in subsets.items()
    }
    required_targets_met = all(
        selections[key]["target_met"]
        for key, contract in subsets.items()
        if contract["required_for_gate"]
    )
    transcript_match_count = sum(
        record["published_transcription_matches_ground_truth"] for record in all_records
    )
    audit: dict[str, Any] = {
        "schema_version": "eval-voice-corpora-v2-source-audit-v1",
        "protocol_id": PROTOCOL_ID,
        "protocol_registry_checksum": protocol_gate["registry_checksum"],
        "source_registry_sha256": file_sha256(root / CONFIG_PATH),
        "status": "METADATA_AUDIT_COMPLETE",
        "audio_dataset_status": "NOT_FROZEN",
        "media_acquisition_status": "BLOCKED_SOURCE_RIGHTS_AND_QUALITY_GATES",
        "model_results": "NOT_RUN",
        "urduspeech": {
            "repository": repository,
            "revision": revision,
            "inventory": summary,
            "subsets": subset_inventory,
            "published_record_count": len(all_records),
            "metadata_files_audited": len(metadata_evidence),
            "metadata_evidence_sha256": record_checksum(metadata_evidence),
            "published_transcription_ground_truth_match_count": transcript_match_count,
            "published_transcription_ground_truth_mismatch_count": (
                len(all_records) - transcript_match_count
            ),
            "exact_audio_duplicate_group_count": len(duplicate_groups),
            "exact_audio_duplicate_groups": duplicate_groups,
            "cross_subset_speaker_identifier_count": len(repeated_identifiers),
            "cross_subset_speaker_identifiers": repeated_identifiers,
            "speaker_identity_interpretation": "UNVERIFIED_IDENTIFIERS_ONLY",
            "human_listening_review": "PENDING",
            "source_media_rights_review": "PENDING",
            "evaluation_independence": "NOT_VERIFIED",
            "required_sample_targets_met": required_targets_met,
            "selections": selections,
        },
        "other_sources": {
            key: registry["sources"][key]
            for key in sorted(registry["sources"])
            if key != "urduspeech"
        },
        "next_gate": (
            "Resolve source-media rights, conduct transcript listening review, audit checkpoint "
            "overlap, and freeze verified audio before model execution."
        ),
    }
    return {**audit, "audit_checksum": record_checksum(audit)}


def render_markdown(audit: dict[str, Any]) -> bytes:
    urdu = audit["urduspeech"]
    selections = urdu["selections"]
    lines = [
        "# EVAL-VOICE-CORPORA-V2 source audit",
        "",
        "| Field | Status |",
        "| --- | --- |",
        f"| Metadata audit | {audit['status']} |",
        f"| Audio dataset | {audit['audio_dataset_status']} |",
        f"| Media acquisition | {audit['media_acquisition_status']} |",
        f"| Model results | {audit['model_results']} |",
        "",
        "## UrduSpeech pinned inventory",
        "",
        f"- Revision: `{urdu['revision']}`",
        f"- Files: {urdu['inventory']['file_count']:,}",
        f"- Audio files: {urdu['inventory']['audio_file_count']:,}",
        f"- Metadata files: {urdu['inventory']['metadata_file_count']:,}",
        f"- Total bytes: {urdu['inventory']['byte_count']:,}",
        f"- Published records: {urdu['published_record_count']:,}",
        (
            "- Published `Transcription`/`ground_truth` mismatches: "
            f"{urdu['published_transcription_ground_truth_mismatch_count']:,}"
        ),
        f"- Exact duplicate-audio groups: {urdu['exact_audio_duplicate_group_count']:,}",
        (
            "- Cross-subset speaker identifiers (identity unverified): "
            f"{urdu['cross_subset_speaker_identifier_count']:,}"
        ),
        "",
        "| Subset | Published records | <=30s eligible | Preview selected | Target |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for key in ("standard_urdu", "code_switched", "pakistani_english"):
        item = selections[key]
        lines.append(
            f"| {key} | {item['source_record_count']} | "
            f"{item['runtime_duration_eligible_count']} | {item['selected_count']} | "
            f"{item['target']} |"
        )
    lines += [
        "",
        "Selections are deterministic previews only. No audio was downloaded, no transcript was",
        "accepted as human-verified through listening, and no dataset or model result was frozen.",
        "Cross-subset speaker labels are identifiers only; they are not treated as verified",
        "people.",
        "",
        "## Other source decisions",
        "",
        "- Common Voice 27 Sindhi: `REFERENCE_ONLY`; 42 test clips; overlap audit pending.",
        "- Pashto Audio-Visual Corpus: `QUARANTINED_AUDIT_ONLY`; rights and listening",
        "  review pending.",
        "- South Asian English: `SOURCE_ID_PENDING`; claimed counts are not frozen evidence.",
        "- SINDHI-HOLDOUT-V1: `PENDING`; 0/100 fresh recordings; model evaluation `NOT_RUN`.",
        "",
        "## Stop condition",
        "",
        audit["next_gate"],
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def audit_sources(root: Path, fetch: Fetch = fetch_url) -> dict[str, Any]:
    audit = build_audit(root, fetch)
    json_path = root / AUDIT_JSON_PATH
    markdown_path = root / AUDIT_MARKDOWN_PATH
    put_json(json_path, audit)
    put_immutable(markdown_path, render_markdown(audit))
    gate = {
        "registry_version": "eval-voice-corpora-v2-audit-gate-v1",
        "protocol_id": PROTOCOL_ID,
        "audit_sha256": file_sha256(json_path),
        "report_sha256": file_sha256(markdown_path),
        "status": audit["status"],
        "audio_dataset_status": "NOT_FROZEN",
        "model_results": "NOT_RUN",
    }
    put_json(root / AUDIT_GATE_PATH, gate)
    return verify_audit(root)


def verify_audit(root: Path) -> dict[str, Any]:
    protocol = verify_protocol(root)
    audit = read_canonical_json(root / AUDIT_JSON_PATH)
    gate = read_canonical_json(root / AUDIT_GATE_PATH)
    if (
        not isinstance(audit, dict)
        or audit.get("protocol_id") != PROTOCOL_ID
        or audit.get("protocol_registry_checksum") != protocol["registry_checksum"]
        or audit.get("audit_checksum")
        != record_checksum({key: value for key, value in audit.items() if key != "audit_checksum"})
        or gate
        != {
            "registry_version": "eval-voice-corpora-v2-audit-gate-v1",
            "protocol_id": PROTOCOL_ID,
            "audit_sha256": file_sha256(root / AUDIT_JSON_PATH),
            "report_sha256": file_sha256(root / AUDIT_MARKDOWN_PATH),
            "status": "METADATA_AUDIT_COMPLETE",
            "audio_dataset_status": "NOT_FROZEN",
            "model_results": "NOT_RUN",
        }
        or (root / AUDIT_MARKDOWN_PATH).read_bytes() != render_markdown(audit)
    ):
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    return gate


def status(root: Path) -> dict[str, Any]:
    protocol = verify_protocol(root)
    result: dict[str, Any] = {
        "protocol_id": PROTOCOL_ID,
        "protocol_status": protocol["status"],
        "metadata_audit": "NOT_RUN",
        "audio_dataset_status": "NOT_FROZEN",
        "model_results": "NOT_RUN",
    }
    if (root / AUDIT_GATE_PATH).exists():
        gate = verify_audit(root)
        result["metadata_audit"] = gate["status"]
    return result
