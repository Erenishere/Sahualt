import hashlib
import json
import urllib.parse
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..benchmark.io import (
    file_sha256,
    put_immutable,
    put_json,
    read_canonical_json,
    record_checksum,
)
from ..corpora_v2.audit import (
    MAX_API_BYTES,
    MAX_METADATA_BYTES,
    fetch_url,
    inventory_summary,
    parse_clean_metadata,
    parse_inventory,
    selection_preview,
)
from ..corpora_v2.registry import load_registry
from ..corpora_v2_readiness.analysis import classify_difference
from ..errors import ErrorCode, VoiceError
from ..transcript import canonical_bytes
from .protocol import (
    PROTOCOL_GATE_PATH,
    PROTOCOL_ID,
    load_config,
    verify_anchors,
    verify_protocol,
)

Fetch = Callable[[str, int], bytes]
SUBSET_ORDER = ("standard_urdu", "code_switched", "pakistani_english")
MODEL_KEYS = ("whisper", "mms")
FORMAT_ONLY = {"UNICODE_NORMALIZATION_ONLY", "PUNCTUATION_OR_WHITESPACE_ONLY"}
GATE_PATH = "configs/gates/eval_voice_corpora_v2_manifest_freeze.json"
MAX_FROZEN_JSON_BYTES = 16 * 1024 * 1024


def _git_blob_id(payload: bytes) -> str:
    return hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()


def _sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _metadata_subset(path: str, subsets: dict[str, Any]) -> str:
    matches = [key for key, item in subsets.items() if path.startswith(item["path"] + "/")]
    if len(matches) != 1:
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    return matches[0]


def _load_pinned_rows(root: Path, fetch: Fetch) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    registry = load_registry(root)
    source = registry["sources"]["urduspeech"]
    repository, revision = source["repository"], source["revision"]
    api_url = f"https://huggingface.co/api/datasets/{repository}/revision/{revision}?blobs=true"
    api_payload = fetch(api_url, MAX_API_BYTES)
    try:
        api_document = json.loads(api_payload.decode("utf-8"))
    except (ValueError, UnicodeError, RecursionError):
        raise VoiceError(ErrorCode.INVALID_MANIFEST) from None
    if (
        not isinstance(api_document, dict)
        or api_document.get("id") != repository
        or api_document.get("sha") != revision
        or api_document.get("private") is not False
        or api_document.get("gated") not in (False, "auto", "manual")
    ):
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    inventory = parse_inventory(api_payload, source["benchmark_root"])
    summary = inventory_summary(inventory)
    if summary != source["expected_inventory"]:
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    audio_assets = {asset["path"]: asset for asset in inventory if "/audio/" in asset["path"]}
    metadata_assets = [
        asset for asset in inventory if asset["path"].endswith("/clean_transcription.jsonl")
    ]
    if len(metadata_assets) * 2 != summary["metadata_file_count"]:
        raise VoiceError(ErrorCode.INVALID_MANIFEST)

    rows: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    source_id_counts: Counter[tuple[str, str]] = Counter()
    for asset in sorted(metadata_assets, key=lambda item: item["path"]):
        metadata_path = asset["path"]
        if "/audio/" in metadata_path:
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        url = (
            f"https://huggingface.co/datasets/{repository}/resolve/{revision}/"
            f"{urllib.parse.quote(metadata_path, safe='/')}"
        )
        payload = fetch(url, MAX_METADATA_BYTES)
        if len(payload) != asset["size"] or _git_blob_id(payload) != asset["blob_id"]:
            raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
        subset = _metadata_subset(metadata_path, source["subsets"])
        parsed = parse_clean_metadata(payload, metadata_path, subset, audio_assets)
        try:
            raw_rows = [json.loads(line) for line in payload.decode("utf-8").splitlines()]
        except (ValueError, UnicodeError, RecursionError):
            raise VoiceError(ErrorCode.INVALID_MANIFEST) from None
        if len(parsed) != len(raw_rows):
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        for line_number, (parsed_row, raw) in enumerate(zip(parsed, raw_rows, strict=True), 1):
            source_id = raw["audio_id"]
            source_identity = (subset, source_id)
            source_id_counts[source_identity] += 1
            if raw["Speaker_id"] != parsed_row["speaker_id"]:
                raise VoiceError(ErrorCode.INVALID_MANIFEST)
            rows.append(
                {
                    **parsed_row,
                    "source_sample_id": source_id,
                    "language": source["subsets"][subset]["language"],
                    "metadata_path": metadata_path,
                    "line_number": line_number,
                    "transcription": raw["Transcription"],
                    "ground_truth": raw["ground_truth"],
                }
            )
        evidence.append(
            {
                "path": metadata_path,
                "size": len(payload),
                "git_blob_id": asset["blob_id"],
                "sha256": hashlib.sha256(payload).hexdigest(),
                "row_count": len(parsed),
            }
        )
    if len(rows) != summary["audio_file_count"] or len({row["audio_path"] for row in rows}) != len(
        rows
    ):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    if len({row["sample_id"] for row in rows}) != len(rows):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    return rows, {
        "inventory": summary,
        "metadata_files": evidence,
        "metadata_evidence_checksum": record_checksum(evidence),
        "repeated_source_sample_id_groups": sum(count > 1 for count in source_id_counts.values()),
    }


def _annotate_rows(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        transcription, reference = row["transcription"], row["ground_truth"]
        exact_match = transcription == reference
        category = None if exact_match else classify_difference(transcription, reference)
        row["transcript_evidence"] = {
            "Transcription": {
                "sha256": _sha_text(transcription),
                "codepoints": len(transcription),
            },
            "ground_truth": {"sha256": _sha_text(reference), "codepoints": len(reference)},
        }
        row["discrepancy_flags"] = {
            "exact_field_match": exact_match,
            "category": category,
            "human_adjudication_required": not exact_match,
            "semantic_review_required": category not in (None, *FORMAT_ONLY),
            "authoritative_reference": (
                "BOTH_SOURCE_FIELDS_IDENTICAL_NOT_INDEPENDENTLY_ADJUDICATED"
                if exact_match
                else "PENDING_HUMAN_ADJUDICATION"
            ),
        }


def select_metadata_rows(
    rows: list[dict[str, Any]],
    subset_contracts: dict[str, Any],
    seed: int,
    max_duration_seconds: int,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    """Select rows deterministically, excluding mismatch, long, and duplicate-audio rows."""
    hash_counts = Counter(row["audio_sha256"] for row in rows)
    duplicate_hashes = {digest for digest, count in hash_counts.items() if count > 1}
    candidates: dict[str, list[dict[str, Any]]] = {key: [] for key in subset_contracts}
    reasons_by_id: dict[str, list[str]] = {}
    for row in rows:
        reasons: list[str] = []
        if not row["discrepancy_flags"]["exact_field_match"]:
            reasons.append("TRANSCRIPT_MISMATCH_UNADJUDICATED")
        if row["audio_sha256"] in duplicate_hashes:
            reasons.append("DUPLICATE_PUBLISHER_AUDIO_SHA256")
        if row["duration_seconds"] > max_duration_seconds:
            reasons.append("DURATION_EXCEEDS_PROTOCOL_LIMIT")
        reasons_by_id[row["sample_id"]] = reasons
        if not reasons:
            candidates[row["subset"]].append(row)

    selected_by_subset: dict[str, list[dict[str, Any]]] = {}
    selected_ids: set[str] = set()
    for subset in SUBSET_ORDER:
        preview = selection_preview(
            candidates[subset],
            subset,
            subset_contracts[subset]["sample_target"],
            seed,
        )
        selected_by_subset[subset] = preview["records"]
        selected_ids.update(record["sample_id"] for record in preview["records"])

    decisions: dict[str, list[dict[str, Any]]] = {key: [] for key in subset_contracts}
    for row in rows:
        reasons = list(reasons_by_id[row["sample_id"]])
        selected = row["sample_id"] in selected_ids
        if not selected and not reasons:
            reasons.append("OUTSIDE_DETERMINISTIC_SAMPLE_TARGET")
        if selected and reasons:
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        decision = {
            "evaluation_record_id": row["sample_id"],
            "source_sample_id": row["source_sample_id"],
            "subset": row["subset"],
            "language": row["language"],
            "speaker_label": row["speaker_id"],
            "speaker_identity_status": "UNVERIFIED_PUBLISHED_LABEL",
            "source_pointer": {
                "metadata_path": row["metadata_path"],
                "line_number": row["line_number"],
                "audio_path": row["audio_path"],
            },
            "transcript_fields": row["transcript_evidence"],
            "discrepancy_flags": row["discrepancy_flags"],
            "selection_decision": "SELECTED" if selected else "EXCLUDED",
            "exclusion_reasons": reasons,
            "publisher_audio_sha256": row["audio_sha256"],
        }
        decisions[row["subset"]].append(decision)
    for records in decisions.values():
        records.sort(key=lambda item: item["evaluation_record_id"])
    if len(selected_ids) != sum(map(len, selected_by_subset.values())):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    selected_hashes = [
        row["audio_sha256"] for values in selected_by_subset.values() for row in values
    ]
    if len(selected_hashes) != len(set(selected_hashes)):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    return selected_by_subset, decisions


def _baseline_models(
    root: Path, readiness: dict[str, Any], source_key: str
) -> list[dict[str, Any]]:
    model_config = json.loads((root / "configs/eval_voice_v1.json").read_text(encoding="utf-8"))
    exposure = readiness["checkpoint_exposure"]["models"]
    result = []
    for key in MODEL_KEYS:
        model = model_config["models"][key]
        exposure_entry = exposure[f"{key}-1b-all" if key == "mms" else "whisper-large-v3"]
        if key == "whisper":
            model_id = "whisper-large-v3"
        else:
            model_id = "mms-1b-all"
        if (
            model["repository"] != exposure_entry["repository"]
            or model["revision"] != exposure_entry["revision"]
        ):
            raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
        result.append(
            {
                "model_id": model_id,
                "repository": model["repository"],
                "revision": model["revision"],
                "source_exposure": exposure_entry["source_exposure"][source_key],
            }
        )
    return result


def _with_checksum(body: dict[str, Any], field: str) -> dict[str, Any]:
    return {**body, field: record_checksum(body)}


def _read_frozen_json(path: Path) -> Any:
    try:
        payload = path.read_bytes()
        if len(payload) > MAX_FROZEN_JSON_BYTES:
            raise VoiceError(ErrorCode.INVALID_MANIFEST)

        def unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
            record: dict[str, object] = {}
            for key, value in pairs:
                if key in record:
                    raise VoiceError(ErrorCode.INVALID_MANIFEST)
                record[key] = value
            return record

        record = json.loads(payload.decode("utf-8"), object_pairs_hook=unique_pairs)
    except VoiceError:
        raise
    except (OSError, ValueError, UnicodeError, RecursionError):
        raise VoiceError(ErrorCode.INVALID_MANIFEST) from None
    try:
        canonical = canonical_bytes(record)
    except (TypeError, ValueError, RecursionError):
        raise VoiceError(ErrorCode.INVALID_MANIFEST) from None
    if payload != canonical:
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    return record


def _manifest(
    subset: str,
    rows: list[dict[str, Any]],
    source: dict[str, Any],
    rights: dict[str, Any],
    models: list[dict[str, Any]],
    protocol_gate: dict[str, Any],
    metadata_evidence_checksum: str,
    seed: int,
) -> dict[str, Any]:
    records = []
    for row in rows:
        records.append(
            {
                "evaluation_record_id": row["sample_id"],
                "source_sample_id": row["source_sample_id"],
                "source_pointer": {
                    "metadata_path": row["metadata_path"],
                    "line_number": row["line_number"],
                    "audio_path": row["audio_path"],
                },
                "publisher_audio_sha256": row["audio_sha256"],
                "audio_size_bytes": row["audio_size"],
                "duration_seconds": row["duration_seconds"],
                "language": row["language"],
                "subset": subset,
                "speaker_label": row["speaker_id"],
                "speaker_identity_status": "UNVERIFIED_PUBLISHED_LABEL",
                "category": row["category"],
                "duration_group": row["duration_group"],
                "transcript_fields": {
                    "Transcription": row["transcription"],
                    "ground_truth": row["ground_truth"],
                },
                "transcript_field_sha256": row["transcript_evidence"],
                "discrepancy_flags": row["discrepancy_flags"],
                "selection_decision": "SELECTED_DETERMINISTIC_STRATIFIED_METADATA_SAMPLE",
            }
        )
    body = {
        "schema_version": "eval-voice-corpora-v2-metadata-manifest-v1",
        "protocol_id": PROTOCOL_ID,
        "status": "FROZEN_METADATA_ONLY_AUDIO_NOT_ACQUIRED",
        "audio_downloaded": False,
        "model_results": "NOT_RUN",
        "selection": {
            "algorithm": "EVAL-VOICE-CORPORA-V2_SELECTION_PREVIEW_V1_AFTER_FROZEN_EXCLUSIONS",
            "seed": seed,
            "target": source["subsets"][subset]["sample_target"],
            "selected_count": len(records),
            "stratification": ["duration_group", "category", "published_speaker_label"],
            "duplicate_policy": "EXCLUDE_ALL_ROWS_SHARING_PUBLISHER_AUDIO_SHA256",
            "transcript_policy": "EXCLUDE_ALL_NON_IDENTICAL_FIELDS_UNTIL_HUMAN_ADJUDICATED",
            "maximum_duration_seconds": 30,
        },
        "source": {
            "source_key": "urduspeech",
            "repository": source["repository"],
            "revision": source["revision"],
            "declared_license": "cc-by-4.0",
            "structured_hub_license": "MISSING",
            "rights_status": "PENDING_SOURCE_MEDIA_RIGHTS_REVIEW",
            "authoritative_rights_record": rights,
            "evaluation_independence": "NOT_VERIFIED",
            "authoritative_reference_status": "PENDING_SOURCE_VALIDATION_AND_HUMAN_ADJUDICATION",
            "metadata_evidence_checksum": metadata_evidence_checksum,
            "publisher_audio_sha256_note": (
                "Publisher inventory LFS metadata only; no audio was downloaded or locally "
                "rehashed."
            ),
        },
        "baseline_models": models,
        "protocol_registry_checksum": protocol_gate["registry_checksum"],
        "records": records,
    }
    return _with_checksum(body, "manifest_content_sha256")


def _artifact_refs(
    root: Path,
    config: dict[str, Any],
    manifests: dict[str, dict[str, Any]],
    decisions: dict[str, list[dict[str, Any]]],
    report_json: dict[str, Any],
    report_markdown: bytes,
) -> dict[str, Any]:
    directory = config["outputs"]["directory"]
    refs: dict[str, Any] = {"manifests": {}, "decision_ledgers": {}}
    for subset in SUBSET_ORDER:
        manifest_rel = f"{directory}/{subset}.json"
        decisions_rel = f"{directory}/decisions/{subset}.json"
        manifest_bytes = canonical_bytes(manifests[subset])
        decisions_bytes = canonical_bytes(decisions[subset])
        refs["manifests"][subset] = {
            "path": manifest_rel,
            "sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "record_count": len(manifests[subset]["records"]),
        }
        refs["decision_ledgers"][subset] = {
            "path": decisions_rel,
            "sha256": hashlib.sha256(decisions_bytes).hexdigest(),
            "record_count": len(decisions[subset]),
        }
    refs["selection_report_json"] = {
        "path": config["outputs"]["selection_report_json"],
        "sha256": hashlib.sha256(canonical_bytes(report_json)).hexdigest(),
    }
    refs["selection_report_markdown"] = {
        "path": config["outputs"]["selection_report_markdown"],
        "sha256": hashlib.sha256(report_markdown).hexdigest(),
    }
    return refs


def _rights_summary(readiness: dict[str, Any], base_registry: dict[str, Any]) -> dict[str, Any]:
    matrix = readiness["rights_matrix"]
    result: dict[str, Any] = {}
    for source_id, source in sorted(base_registry["sources"].items()):
        rights_record = matrix[source_id]
        result[source_id] = {
            "source_status": source.get(
                "status",
                source.get("acquisition_status", source.get("protocol_status", "NOT_STATED")),
            ),
            "acquisition_status": source.get("acquisition_status", "NOT_STATED"),
            "evaluation_independence": source.get("evaluation_independence", "NOT_VERIFIED"),
            "evaluation_status": source.get("evaluation_status", "NOT_STATED"),
            "rights": rights_record,
            "manifest_frozen": False,
            "gate_status": "BLOCKED_NO_FROZEN_SELECTED_MANIFEST",
        }
    result["urduspeech"]["manifest_frozen"] = True
    result["urduspeech"]["gate_status"] = "BLOCKED_RIGHTS_AND_INDEPENDENCE_UNRESOLVED"
    return result


def acquisition_blockers(source_status: dict[str, Any], *, manifest_frozen: bool) -> list[str]:
    blockers: list[str] = []
    rights = source_status.get("rights", {}).get("rights", {})
    local_use = rights.get("local_asr_evaluation", "NOT_DOCUMENTED")
    if local_use != "ALLOWED":
        blockers.append("LOCAL_EVALUATION_RIGHTS_NOT_EXPLICITLY_UNCONDITIONAL")
    if source_status.get("evaluation_independence") != "VERIFIED":
        blockers.append("EVALUATION_INDEPENDENCE_UNRESOLVED")
    if not manifest_frozen:
        blockers.append("SELECTED_METADATA_MANIFEST_NOT_FROZEN")
    status = str(source_status.get("source_status", "NOT_STATED"))
    if status in {"BLOCKED", "REFERENCE_ONLY", "QUARANTINED_AUDIT_ONLY", "PENDING"}:
        blockers.append(f"SOURCE_STATUS_{status}")
    if source_status.get("acquisition_status") in {"BLOCKED", "BLOCKED_SOURCE_AUDIT"}:
        blockers.append("SOURCE_REGISTRY_ACQUISITION_BLOCKED")
    if source_status.get("evaluation_status") in {"REFERENCE_ONLY", "QUARANTINED_AUDIT_ONLY"}:
        blockers.append(f"EVALUATION_STATUS_{source_status['evaluation_status']}")
    return blockers


def require_acquisition_ready(source_status: dict[str, Any], *, manifest_frozen: bool) -> None:
    if acquisition_blockers(source_status, manifest_frozen=manifest_frozen):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)


def _render_report_markdown(report: dict[str, Any]) -> bytes:
    lines = [
        "# EVAL-VOICE-CORPORA-V2 manifest selection and exclusion report",
        "",
        f"**Metadata manifest status:** `{report['status']}`",
        "",
        "No audio was downloaded; no ASR model was executed or fine-tuned.",
        "Publisher audio SHA-256 values are inventory metadata and were not locally rehashed.",
        "Speaker labels are retained as published identifiers, not treated as verified people.",
        "",
        "## Reconciliation and selected counts",
        "",
        f"- Full pinned UrduSpeech benchmark inventory: "
        f"{report['published_record_count']:,} records.",
        f"- Previously audited preview count: {report['prior_preview_count']:,} (200 + 200 + 144).",
        f"- Exact `Transcription`/`ground_truth` matches: "
        f"{report['exact_transcript_match_count']:,}.",
        f"- Mismatched transcript rows excluded: {report['transcript_mismatch_count']:,}.",
        f"- Duplicate publisher audio-hash groups: {report['duplicate_audio_group_count']:,}.",
        "",
        "| Subset | Published | Eligible | Selected | Target | Target met | Excluded |",
        "| --- | ---: | ---: | ---: | ---: | --- | ---: |",
    ]
    for subset in SUBSET_ORDER:
        item = report["subsets"][subset]
        lines.append(
            f"| {subset} | {item['published_count']:,} | {item['eligible_count']:,} | "
            f"{item['selected_count']:,} | {item['target']:,} | "
            f"{'yes' if item['target_met'] else 'no'} | {item['excluded_count']:,} |"
        )
    lines += [
        "",
        "The full record-level decision trail is stored in the three canonical subset ledgers "
        "linked",
        "by the frozen registry. Each row records source IDs and pointers, published speaker "
        "label,",
        "both transcript-field hashes and lengths, discrepancy classification, decision, and "
        "reason.",
        "Mismatched transcript strings are not copied to the exclusion ledgers and are not "
        "resolved",
        "automatically. Selected manifests contain both exact-matching source transcript fields.",
        "",
        "## Exclusion reasons",
        "",
    ]
    for reason, count in sorted(report["exclusion_reason_counts"].items()):
        lines.append(f"- `{reason}`: {count:,} record decisions.")
    lines += [
        "",
        "## Source rights and acquisition gate",
        "",
        "Source rights records are copied from the pinned acquisition-readiness report without",
        "reinterpreting or upgrading their status. The UrduSpeech rights review and evaluation",
        "independence remain unresolved. Metadata-manifest freeze is not "
        "audio-acquisition approval.",
        "The acquisition gate remains BLOCKED for every current source.",
        "",
        "## Remaining source coverage",
        "",
        "South Asian English, Pashto, Common Voice Sindhi, and the fresh Sindhi holdout have no",
        "frozen selected metadata manifest in this bundle. Their authoritative source and rights",
        "statuses remain in the gate; acquisition remains rejected until their source-specific",
        "metadata, permissions, revisions, and independent-sample gates are resolved.",
        "",
    ]
    return ("\n".join(lines)).encode("utf-8")


def _gate_record(
    root: Path,
    config: dict[str, Any],
    registry_record: dict[str, Any],
    readiness: dict[str, Any],
    base_registry: dict[str, Any],
) -> dict[str, Any]:
    statuses = _rights_summary(readiness, base_registry)
    manifest_frozen = {subset: True for subset in SUBSET_ORDER}
    for source_id, status in statuses.items():
        frozen = source_id == "urduspeech" and all(manifest_frozen.values())
        blockers = acquisition_blockers(status, manifest_frozen=frozen)
        status["manifest_frozen"] = frozen
        status["acquisition_blockers"] = blockers
        if not blockers:
            status["gate_status"] = "ACQUISITION_READY"
        elif not frozen:
            status["gate_status"] = "BLOCKED_NO_FROZEN_SELECTED_MANIFEST"
        else:
            status["gate_status"] = "BLOCKED_RIGHTS_AND_INDEPENDENCE_UNRESOLVED"
    body: dict[str, Any] = {
        "registry_version": "eval-voice-corpora-v2-manifest-freeze-gate-v1",
        "protocol_id": PROTOCOL_ID,
        "status": "METADATA_MANIFESTS_FROZEN_ACQUISITION_BLOCKED",
        "metadata_manifests_frozen": True,
        "audio_dataset_status": "NOT_ACQUIRED",
        "audio_downloaded": False,
        "model_results": "NOT_RUN",
        "fine_tuning": "NOT_AUTHORIZED",
        "registry_path": config["outputs"]["registry"],
        "registry_sha256": hashlib.sha256(canonical_bytes(registry_record)).hexdigest(),
        "registry_checksum": registry_record["registry_checksum"],
        "readiness_gate_status": "BLOCKED_UNCHANGED",
        "readiness_gate_sha256": file_sha256(
            root / "configs/gates/eval_voice_corpora_v2_readiness.json"
        ),
        "source_statuses": statuses,
        "acquisition_gate": {
            "status": "BLOCKED",
            "ready_source_ids": [],
            "blocked_source_ids": sorted(statuses),
            "rule": (
                "Require a frozen selected manifest, verified independent evaluation source, "
                "and explicit unconditional local-evaluation authorization."
            ),
        },
    }
    return _with_checksum(body, "gate_checksum")


def freeze(root: Path, fetch: Fetch = fetch_url) -> dict[str, Any]:
    config = load_config(root)
    if (root / config["outputs"]["registry"]).exists():
        return verify_freeze(root)
    protocol_gate = verify_protocol(root)
    readiness = verify_anchors(root, config)
    base_registry = load_registry(root)
    rows, source_evidence = _load_pinned_rows(root, fetch)
    if len(rows) != 4170:
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    _annotate_rows(rows)
    selected_by_subset, decisions = select_metadata_rows(
        rows,
        base_registry["sources"]["urduspeech"]["subsets"],
        config["protocol"]["seed"],
        config["protocol"]["max_duration_seconds"],
    )
    source = base_registry["sources"]["urduspeech"]
    rights = readiness["rights_matrix"]["urduspeech"]
    models = _baseline_models(root, readiness, "urduspeech")
    manifests = {
        subset: _manifest(
            subset,
            selected_by_subset[subset],
            source,
            rights,
            models,
            protocol_gate,
            source_evidence["metadata_evidence_checksum"],
            config["protocol"]["seed"],
        )
        for subset in SUBSET_ORDER
    }
    record_counts = Counter(row["subset"] for row in rows)
    transcript_matches = sum(row["discrepancy_flags"]["exact_field_match"] for row in rows)
    duplicate_counts = Counter(row["audio_sha256"] for row in rows)
    duplicate_groups = sum(count > 1 for count in duplicate_counts.values())
    reason_counts: Counter[str] = Counter()
    for subset_decisions in decisions.values():
        for decision in subset_decisions:
            reason_counts.update(decision["exclusion_reasons"])
    subset_report = {}
    for subset in SUBSET_ORDER:
        selected_count = len(selected_by_subset[subset])
        target = source["subsets"][subset]["sample_target"]
        eligible_count = sum(
            decision["selection_decision"] == "SELECTED"
            or decision["exclusion_reasons"] == ["OUTSIDE_DETERMINISTIC_SAMPLE_TARGET"]
            for decision in decisions[subset]
        )
        subset_report[subset] = {
            "published_count": record_counts[subset],
            "eligible_count": eligible_count,
            "selected_count": selected_count,
            "target": target,
            "target_met": selected_count == target,
            "excluded_count": record_counts[subset] - selected_count,
        }
    prior_audit = read_canonical_json(root / "reports/eval_voice_corpora_v2_source_audit.json")
    body = {
        "schema_version": "eval-voice-corpora-v2-selection-exclusion-report-v1",
        "protocol_id": PROTOCOL_ID,
        "status": "FROZEN_METADATA_ONLY_AUDIO_NOT_ACQUIRED",
        "audio_downloaded": False,
        "model_results": "NOT_RUN",
        "source_key": "urduspeech",
        "repository": source["repository"],
        "revision": source["revision"],
        "source_inventory": source_evidence["inventory"],
        "metadata_evidence": source_evidence["metadata_files"],
        "metadata_evidence_checksum": source_evidence["metadata_evidence_checksum"],
        "published_record_count": len(rows),
        "prior_preview_count": sum(
            item["selected_count"] for item in prior_audit["urduspeech"]["selections"].values()
        ),
        "exact_transcript_match_count": transcript_matches,
        "transcript_mismatch_count": len(rows) - transcript_matches,
        "duplicate_audio_group_count": duplicate_groups,
        "repeated_source_sample_id_groups": source_evidence["repeated_source_sample_id_groups"],
        "publisher_audio_hash_is_local_fingerprint": False,
        "speaker_labels_are_verified_identities": False,
        "subsets": subset_report,
        "exclusion_reason_counts": dict(sorted(reason_counts.items())),
        "selection_seed": config["protocol"]["seed"],
        "selection_algorithm": "EVAL-VOICE-CORPORA-V2_SELECTION_PREVIEW_V1_AFTER_FROZEN_EXCLUSIONS",
    }
    report_body = _with_checksum(body, "report_checksum")
    markdown = _render_report_markdown(report_body)
    refs = _artifact_refs(root, config, manifests, decisions, report_body, markdown)
    rights_matrix = readiness["rights_matrix"]
    registry_body = {
        "registry_version": "eval-voice-corpora-v2-frozen-manifest-registry-v1",
        "protocol_id": PROTOCOL_ID,
        "protocol_gate_path": PROTOCOL_GATE_PATH,
        "protocol_gate_sha256": file_sha256(root / PROTOCOL_GATE_PATH),
        "source_registry_sha256": file_sha256(root / "configs/voice_corpora_v2.json"),
        "source_key": "urduspeech",
        "source_repository": source["repository"],
        "source_revision": source["revision"],
        "source_rights_status_authoritative": rights_matrix,
        "selection_exclusion_report": refs["selection_report_json"],
        "selection_exclusion_report_markdown": refs["selection_report_markdown"],
        "manifests": refs["manifests"],
        "decision_ledgers": refs["decision_ledgers"],
        "source_coverage": {
            source_id: {
                "status": "MANIFESTED" if source_id == "urduspeech" else "NOT_MANIFESTED",
                "reason": (
                    "Pinned metadata source audited and frozen; audio acquisition remains blocked."
                    if source_id == "urduspeech"
                    else "No selected pinned metadata manifest frozen in this phase."
                ),
            }
            for source_id in sorted(base_registry["sources"])
        },
        "audio_downloaded": False,
        "model_results": "NOT_RUN",
    }
    registry_record = _with_checksum(registry_body, "registry_checksum")
    gate = _gate_record(root, config, registry_record, readiness, base_registry)

    for subset in SUBSET_ORDER:
        put_json(root / refs["manifests"][subset]["path"], manifests[subset])
        put_json(root / refs["decision_ledgers"][subset]["path"], decisions[subset])
    put_json(root / refs["selection_report_json"]["path"], report_body)
    put_immutable(root / refs["selection_report_markdown"]["path"], markdown)
    put_json(root / config["outputs"]["registry"], registry_record)
    put_json(root / config["outputs"]["gate"], gate)
    return verify_freeze(root)


def _verify_hash_refs(root: Path, references: dict[str, Any]) -> None:
    for reference in references.values():
        path = root / reference["path"]
        if file_sha256(path) != reference["sha256"]:
            raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
        if path.suffix == ".json":
            _read_frozen_json(path)


def verify_freeze(root: Path) -> dict[str, Any]:
    config = load_config(root)
    protocol_gate = verify_protocol(root)
    readiness = verify_anchors(root, config)
    registry_path = root / config["outputs"]["registry"]
    registry_record = _read_frozen_json(registry_path)
    registry_body = {
        key: value for key, value in registry_record.items() if key != "registry_checksum"
    }
    if (
        registry_record.get("registry_checksum") != record_checksum(registry_body)
        or registry_record.get("protocol_gate_path")
        != config["protocol"]["amendment"]["supersedes_gate_path"]
        or registry_record.get("protocol_gate_sha256")
        != file_sha256(root / registry_record["protocol_gate_path"])
        or registry_record.get("source_revision") != config["source"]["revision"]
        or registry_record.get("source_rights_status_authoritative") != readiness["rights_matrix"]
    ):
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    manifest_generation_gate = _read_frozen_json(root / registry_record["protocol_gate_path"])
    generation_gate_body = {
        key: value for key, value in manifest_generation_gate.items() if key != "registry_checksum"
    }
    if manifest_generation_gate.get("registry_checksum") != record_checksum(generation_gate_body):
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    _verify_hash_refs(root, registry_record["manifests"])
    _verify_hash_refs(root, registry_record["decision_ledgers"])
    _verify_hash_refs(root, {"report": registry_record["selection_exclusion_report"]})
    _verify_hash_refs(root, {"markdown": registry_record["selection_exclusion_report_markdown"]})
    report = _read_frozen_json(root / registry_record["selection_exclusion_report"]["path"])
    report_body = {key: value for key, value in report.items() if key != "report_checksum"}
    if report.get("report_checksum") != record_checksum(report_body):
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)

    selected_ids_by_subset: dict[str, list[str]] = {}
    all_selected_hashes: list[str] = []
    decision_total = 0
    for subset in SUBSET_ORDER:
        manifest_ref = registry_record["manifests"][subset]
        manifest = _read_frozen_json(root / manifest_ref["path"])
        manifest_body = {
            key: value for key, value in manifest.items() if key != "manifest_content_sha256"
        }
        if (
            manifest.get("manifest_content_sha256") != record_checksum(manifest_body)
            or manifest.get("source", {}).get("revision") != config["source"]["revision"]
            or manifest.get("audio_downloaded") is not False
            or manifest.get("status") != "FROZEN_METADATA_ONLY_AUDIO_NOT_ACQUIRED"
            or manifest.get("protocol_registry_checksum")
            != manifest_generation_gate["registry_checksum"]
        ):
            raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
        records = manifest["records"]
        ids = [record["evaluation_record_id"] for record in records]
        hashes = [record["publisher_audio_sha256"] for record in records]
        if len(ids) != len(set(ids)) or len(hashes) != len(set(hashes)):
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        selected_ids_by_subset[subset] = ids
        all_selected_hashes.extend(hashes)
        ledger_ref = registry_record["decision_ledgers"][subset]
        ledger = _read_frozen_json(root / ledger_ref["path"])
        if not isinstance(ledger, list):
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        decision_total += len(ledger)
        selected_from_ledger = [
            row["evaluation_record_id"] for row in ledger if row["selection_decision"] == "SELECTED"
        ]
        if set(selected_from_ledger) != set(ids) or any(
            row["selection_decision"] == "EXCLUDED" and not row["exclusion_reasons"]
            for row in ledger
        ):
            raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
        if any(
            record["transcript_fields"]["Transcription"]
            != record["transcript_fields"]["ground_truth"]
            for record in records
        ):
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
    if len(all_selected_hashes) != len(set(all_selected_hashes)) or decision_total != 4170:
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    base_registry = load_registry(root)
    gate = _read_frozen_json(root / config["outputs"]["gate"])
    expected_gate = _gate_record(root, config, registry_record, readiness, base_registry)
    if gate != expected_gate:
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    gate_body = {key: value for key, value in gate.items() if key != "gate_checksum"}
    if gate.get("gate_checksum") != record_checksum(gate_body):
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    return {
        "status": gate["status"],
        "protocol_id": PROTOCOL_ID,
        "protocol_registry_checksum": manifest_generation_gate["registry_checksum"],
        "verification_protocol_registry_checksum": protocol_gate["registry_checksum"],
        "registry_checksum": registry_record["registry_checksum"],
        "manifest_counts": {subset: len(selected_ids_by_subset[subset]) for subset in SUBSET_ORDER},
        "decision_count": decision_total,
        "acquisition_gate": gate["acquisition_gate"]["status"],
        "audio_downloaded": gate["audio_downloaded"],
        "model_results": gate["model_results"],
    }
