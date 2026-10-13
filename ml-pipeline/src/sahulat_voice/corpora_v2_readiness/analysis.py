import hashlib
import itertools
import json
import unicodedata
import urllib.parse
from collections import Counter, defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..benchmark.io import (
    file_sha256,
    put_immutable,
    put_json,
    read_canonical_json,
    read_json,
    record_checksum,
)
from ..corpora_v2.audit import (
    MAX_API_BYTES,
    MAX_METADATA_BYTES,
    fetch_url,
    inventory_summary,
    parse_clean_metadata,
    parse_inventory,
)
from ..corpora_v2.audit import (
    verify_audit as verify_base_audit,
)
from ..corpora_v2.registry import AUDIT_JSON_PATH, load_registry
from ..errors import ErrorCode, VoiceError
from .protocol import (
    AMENDMENT_ID,
    PROTOCOL_ID,
    READINESS_GATE_PATH,
    READINESS_JSON_PATH,
    READINESS_MARKDOWN_PATH,
    load_config,
    verify_protocol,
)

Fetch = Callable[[str, int], bytes]
SUBSET_ORDER = ("standard_urdu", "code_switched", "pakistani_english")
FORMAT_ONLY = {"UNICODE_NORMALIZATION_ONLY", "PUNCTUATION_OR_WHITESPACE_ONLY"}


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _git_blob_id(payload: bytes) -> str:
    return hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()


def _tokens(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFC", value).casefold()
    without_punctuation = "".join(
        " " if unicodedata.category(character).startswith("P") else character
        for character in normalized
    )
    return without_punctuation.split()


def _script_profile(value: str) -> tuple[str, ...]:
    scripts: set[str] = set()
    for character in unicodedata.normalize("NFC", value):
        name = unicodedata.name(character, "")
        if "ARABIC" in name:
            scripts.add("ARABIC")
        elif "LATIN" in name:
            scripts.add("LATIN")
        elif character.isalpha():
            scripts.add("OTHER_LETTER")
    return tuple(sorted(scripts))


def _is_subsequence(shorter: list[str], longer: list[str]) -> bool:
    iterator = iter(longer)
    return all(any(candidate == token for candidate in iterator) for token in shorter)


def classify_difference(transcription: str, ground_truth: str) -> str:
    if transcription == ground_truth:
        raise ValueError("classification requires different strings")
    transcription_nfc = unicodedata.normalize("NFC", transcription)
    ground_truth_nfc = unicodedata.normalize("NFC", ground_truth)
    if transcription_nfc == ground_truth_nfc:
        return "UNICODE_NORMALIZATION_ONLY"
    transcription_tokens = _tokens(transcription_nfc)
    ground_truth_tokens = _tokens(ground_truth_nfc)
    if transcription_tokens == ground_truth_tokens:
        return "PUNCTUATION_OR_WHITESPACE_ONLY"
    if _script_profile(transcription_nfc) != _script_profile(ground_truth_nfc):
        return "SCRIPT_PROFILE_CHANGE"
    if len(transcription_tokens) != len(ground_truth_tokens) and (
        _is_subsequence(transcription_tokens, ground_truth_tokens)
        or _is_subsequence(ground_truth_tokens, transcription_tokens)
        or Counter(transcription_tokens) <= Counter(ground_truth_tokens)
        or Counter(ground_truth_tokens) <= Counter(transcription_tokens)
    ):
        return "MISSING_OR_ADDED_WORDS"
    if len(transcription_tokens) == len(ground_truth_tokens):
        return "SPELLING_OR_TOKEN_SUBSTITUTION"
    return "SEMANTIC_REVIEW_REQUIRED"


def _subset_for_path(path: str, subsets: dict[str, Any]) -> str:
    matches = [key for key, value in subsets.items() if path.startswith(value["path"] + "/")]
    if len(matches) != 1:
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    return matches[0]


def _load_pinned_rows(root: Path, fetch: Fetch) -> list[dict[str, Any]]:
    registry = load_registry(root)
    urdu = registry["sources"]["urduspeech"]
    repository, revision = urdu["repository"], urdu["revision"]
    api_url = f"https://huggingface.co/api/datasets/{repository}/revision/{revision}?blobs=true"
    api_payload = fetch(api_url, MAX_API_BYTES)
    try:
        api_document = json.loads(api_payload.decode("utf-8"))
    except (ValueError, UnicodeError):
        raise VoiceError(ErrorCode.INVALID_MANIFEST) from None
    if not isinstance(api_document, dict) or api_document.get("sha") != revision:
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    inventory = parse_inventory(api_payload, urdu["benchmark_root"])
    if inventory_summary(inventory) != urdu["expected_inventory"]:
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    audio_assets = {item["path"]: item for item in inventory if "/audio/" in item["path"]}
    metadata_assets = [
        item for item in inventory if item["path"].endswith("/clean_transcription.jsonl")
    ]
    rows: list[dict[str, Any]] = []
    for asset in sorted(metadata_assets, key=lambda item: item["path"]):
        path = asset["path"]
        url = (
            f"https://huggingface.co/datasets/{repository}/resolve/{revision}/"
            f"{urllib.parse.quote(path, safe='/')}"
        )
        payload = fetch(url, MAX_METADATA_BYTES)
        if len(payload) != asset["size"] or _git_blob_id(payload) != asset["blob_id"]:
            raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
        subset = _subset_for_path(path, urdu["subsets"])
        parsed = parse_clean_metadata(payload, path, subset, audio_assets)
        try:
            published = [json.loads(line) for line in payload.decode("utf-8").splitlines()]
        except (ValueError, UnicodeError):
            raise VoiceError(ErrorCode.INVALID_MANIFEST) from None
        if len(parsed) != len(published):
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        for line_number, (base, source) in enumerate(zip(parsed, published, strict=True), start=1):
            transcription, ground_truth = source["Transcription"], source["ground_truth"]
            rows.append(
                {
                    **base,
                    "metadata_path": path,
                    "line_number": line_number,
                    "transcription": transcription,
                    "ground_truth": ground_truth,
                }
            )
    return rows


def _difference_record(row: dict[str, Any]) -> dict[str, Any]:
    transcription, ground_truth = row["transcription"], row["ground_truth"]
    category = classify_difference(transcription, ground_truth)
    return {
        "sample_id": row["sample_id"],
        "subset": row["subset"],
        "source_pointer": {
            "metadata_path": row["metadata_path"],
            "line_number": row["line_number"],
            "audio_path": row["audio_path"],
        },
        "transcription_sha256": _sha256_text(transcription),
        "ground_truth_sha256": _sha256_text(ground_truth),
        "transcription_codepoints": len(transcription),
        "ground_truth_codepoints": len(ground_truth),
        "transcription_tokens": len(_tokens(transcription)),
        "ground_truth_tokens": len(_tokens(ground_truth)),
        "classification": category,
        "semantic_review": "NOT_REQUIRED_FORMAT_ONLY" if category in FORMAT_ONLY else "REQUIRED",
        "adjudication": "PENDING",
        "authoritative_reference": "PENDING_HUMAN_ADJUDICATION",
    }


def _speaker_audit(rows: list[dict[str, Any]], base_audit: dict[str, Any]) -> dict[str, Any]:
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        counts[row["speaker_id"]][row["subset"]] += 1
    selected_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for subset, preview in base_audit["urduspeech"]["selections"].items():
        for row in preview["records"]:
            selected_counts[row["speaker_id"]][subset] += 1
    repeated = {
        speaker: subset_counts
        for speaker, subset_counts in counts.items()
        if len(subset_counts) > 1
    }
    pair_counts: dict[str, int] = {}
    for left, right in itertools.combinations(SUBSET_ORDER, 2):
        pair_counts[f"{left}__{right}"] = sum(
            left in subset_counts and right in subset_counts for subset_counts in repeated.values()
        )
    pattern_counts = Counter("+".join(sorted(value)) for value in repeated.values())
    records = []
    for speaker, subset_counts in sorted(repeated.items()):
        records.append(
            {
                "identifier_sha256": _sha256_text(f"{PROTOCOL_ID}|speaker|{speaker}"),
                "subsets": sorted(subset_counts),
                "published_record_counts": dict(sorted(subset_counts.items())),
                "selected_preview_counts": dict(sorted(selected_counts[speaker].items())),
            }
        )
    selected_repeated = sum(len(value) > 1 for value in selected_counts.values())
    return {
        "cross_subset_identifier_count": len(repeated),
        "identifier_interpretation": "UNVERIFIED_PUBLISHED_LABEL_NOT_VERIFIED_PERSON",
        "subset_unique_identifier_counts": {
            subset: len({row["speaker_id"] for row in rows if row["subset"] == subset})
            for subset in SUBSET_ORDER
        },
        "pair_identifier_counts": pair_counts,
        "subset_pattern_counts": dict(sorted(pattern_counts.items())),
        "selected_preview_cross_subset_identifier_count": selected_repeated,
        "records": records,
        "pooled_reporting_rule": (
            "Report subsets separately. Do not claim speaker-independent pooled estimates unless "
            "publisher identifier namespaces are resolved to people; then group or exclude "
            "overlaps."
        ),
    }


def _verify_checkpoint_pins(root: Path, config: dict[str, Any]) -> None:
    primary = read_json(root / "configs/eval_voice_v1.json")["models"]
    alternatives = read_json(root / "configs/voice_alt_v1_models.json")["models"]
    expected = config["checkpoint_exposure"]["models"]
    actual = {
        "whisper-large-v3": primary["whisper"],
        "mms-1b-all": primary["mms"],
        "pashto-ghag": alternatives["pashto-ghag"],
        "buzzasr-sindhi": alternatives["buzzasr-sindhi"],
    }
    for key, source in actual.items():
        if (
            source["repository"] != expected[key]["repository"]
            or source["revision"] != expected[key]["revision"]
        ):
            raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)


def build_readiness(root: Path, fetch: Fetch = fetch_url) -> dict[str, Any]:
    protocol_gate = verify_protocol(root)
    verify_base_audit(root)
    config = load_config(root)
    _verify_checkpoint_pins(root, config)
    base_audit = read_canonical_json(root / AUDIT_JSON_PATH)
    rows = _load_pinned_rows(root, fetch)
    if len(rows) != 4170:
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)

    differences = [
        _difference_record(row) for row in rows if row["transcription"] != row["ground_truth"]
    ]
    if len(differences) != 379:
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    category_counts = Counter(record["classification"] for record in differences)
    subset_counts = Counter(record["subset"] for record in differences)
    format_only_count = sum(
        count for category, count in category_counts.items() if category in FORMAT_ONLY
    )
    speaker_audit = _speaker_audit(rows, base_audit)
    if speaker_audit["cross_subset_identifier_count"] != 37:
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)

    selections = base_audit["urduspeech"]["selections"]
    published = sum(item["source_record_count"] for item in selections.values())
    eligible = sum(item["runtime_duration_eligible_count"] for item in selections.values())
    selected = sum(item["selected_count"] for item in selections.values())
    criteria = {
        "dataset_provenance_and_rights_approved": False,
        "transcript_discrepancies_adjudicated_or_excluded_in_frozen_manifest": False,
        "speaker_overlap_risk_documented": True,
        "checkpoint_overlap_risk_documented": True,
        "selected_evaluation_manifests_frozen": False,
        "sindhi_collection_protocol_approved": True,
    }
    blockers = [
        "UrduSpeech source-media rights and Pashto consent/redistribution review remain pending.",
        "Non-identical UrduSpeech transcript fields are not human-adjudicated and are excluded.",
        "Selected audio evaluation manifests are previews and are not frozen.",
    ]
    body: dict[str, Any] = {
        "schema_version": "eval-voice-corpora-v2-readiness-report-v1",
        "protocol_id": PROTOCOL_ID,
        "amendment_id": AMENDMENT_ID,
        "protocol_registry_checksum": protocol_gate["registry_checksum"],
        "status": "BLOCKED",
        "target_status": "AUDIO_ACQUISITION_READY",
        "audio_dataset_status": "NOT_FROZEN",
        "audio_downloaded": False,
        "model_results": "NOT_RUN",
        "fine_tuning": "NOT_AUTHORIZED",
        "record_reconciliation": {
            "published_records": published,
            "duration_eligible_records": eligible,
            "duration_ineligible_records": published - eligible,
            "preview_selected_records": selected,
            "published_not_in_preview": published - selected,
            "eligible_not_in_preview": eligible - selected,
            "preview_breakdown": {
                subset: {
                    "published": selections[subset]["source_record_count"],
                    "duration_eligible": selections[subset]["runtime_duration_eligible_count"],
                    "selected": selections[subset]["selected_count"],
                    "target": selections[subset]["target"],
                }
                for subset in SUBSET_ORDER
            },
        },
        "south_asian_english": config["sources"]["south_asian_english"],
        "transcript_differences": {
            "published_match_count": published - len(differences),
            "published_mismatch_count": len(differences),
            "category_counts": dict(sorted(category_counts.items())),
            "subset_counts": dict(sorted(subset_counts.items())),
            "format_only_count": format_only_count,
            "semantic_review_required_count": len(differences) - format_only_count,
            "semantic_difference_confirmed_count": 0,
            "semantic_classification": "HUMAN_ONLY_NOT_INFERRED",
            "authoritative_reference": "PENDING_HUMAN_ADJUDICATION",
            "scoring_policy": "EXCLUDE_MISMATCHED_ROWS_UNTIL_ADJUDICATED_AND_FROZEN",
            "raw_text_stored_in_report": False,
            "record_manifest_checksum": record_checksum(differences),
            "records": differences,
        },
        "speaker_overlap": speaker_audit,
        "rights_matrix": {
            key: {
                field: value
                for field, value in source.items()
                if field
                in {
                    "source_url",
                    "declared_license",
                    "rights",
                    "rights_status",
                    "evaluation_status",
                    "acquisition_status",
                    "protocol_status",
                }
            }
            for key, source in sorted(config["sources"].items())
        },
        "checkpoint_exposure": config["checkpoint_exposure"],
        "sindhi_holdout_protocol": {
            "status": "APPROVED_DATA_PENDING",
            "recordings": "0/100",
            "speakers": "0/10",
            "model_evaluation": "NOT_RUN",
            "collection_requirements": [
                "Human-authored Perso-Arabic Sindhi references with independent review",
                "Fresh 16 kHz mono PCM16 WAV recordings with consent and use permission",
                "Ten pseudonymous speakers; two speakers per utterance; ten recordings each",
                "Thirty commerce utterances and twenty everyday utterances",
                "Public-corpus participation attestations retained as risk evidence",
                "No FLEURS, Common Voice, TTS, translated benchmark, or model-generated source",
            ],
        },
        "gate_criteria": criteria,
        "blockers": blockers,
    }
    return {**body, "readiness_checksum": record_checksum(body)}


def render_markdown(report: dict[str, Any]) -> bytes:
    reconciliation = report["record_reconciliation"]
    differences = report["transcript_differences"]
    speakers = report["speaker_overlap"]
    english = report["south_asian_english"]
    lines = [
        "# EVAL-VOICE-CORPORA-V2 — audio acquisition readiness",
        "",
        f"**Gate: {report['status']}** (target: `{report['target_status']}`)",
        "",
        "No audio was downloaded, no model was run, and fine-tuning remains unauthorized.",
        "",
        "## Record reconciliation",
        "",
        "| Population | Count |",
        "| --- | ---: |",
        f"| Published UrduSpeech benchmark records | {reconciliation['published_records']:,} |",
        f"| Runtime-eligible (<=30s) | {reconciliation['duration_eligible_records']:,} |",
        f"| Duration-ineligible | {reconciliation['duration_ineligible_records']:,} |",
        f"| Deterministic preview selected | {reconciliation['preview_selected_records']:,} |",
        f"| Published records outside preview | {reconciliation['published_not_in_preview']:,} |",
        "",
        "The 544-record preview is 200 Standard Urdu + 200 code-switched + all 144",
        "Pakistani-English records. It is a subset of the 4,170-record published inventory.",
        "",
        "## Transcript field audit",
        "",
        f"- Exact matches: {differences['published_match_count']:,}",
        f"- Differences: {differences['published_mismatch_count']:,}",
        f"- Format-only: {differences['format_only_count']:,}",
        f"- Human semantic review required: {differences['semantic_review_required_count']:,}",
        "- Confirmed semantic differences: 0 (not inferred automatically)",
        "- Authoritative scoring reference: `PENDING_HUMAN_ADJUDICATION`",
        "",
        "| Classification | Count |",
        "| --- | ---: |",
    ]
    for category, count in differences["category_counts"].items():
        lines.append(f"| {category} | {count} |")
    lines += [
        "",
        "Both source fields remain independently hash-addressed with pinned file/line pointers.",
        "Raw transcript text is not copied into this report. Mismatched rows are excluded from",
        "scoring until a human adjudication manifest selects a reference and is frozen.",
        "",
        "## Cross-subset speaker labels",
        "",
        f"- Repeated published identifiers: {speakers['cross_subset_identifier_count']}",
        (
            "- Repeated identifiers in the 544-record preview: "
            f"{speakers['selected_preview_cross_subset_identifier_count']}"
        ),
        "- Identity meaning: unverified label, not a verified person",
        "- Reporting rule: keep subsets separate; do not claim pooled speaker independence.",
        "",
        "| Subset pair | Shared identifiers |",
        "| --- | ---: |",
    ]
    for pair, count in sorted(speakers["pair_identifier_counts"].items()):
        lines.append(f"| {pair.replace('__', ' / ')} | {count} |")
    rights_rows = report["rights_matrix"]
    lines += [
        "",
        "## South Asian English source",
        "",
        f"- Dataset ID: `{english['dataset_id']}`",
        f"- Test split: {english['test_clips']:,} clips, {english['test_speakers']} speakers, "
        f"{english['test_hours']} hours",
        "- Scope: India, Pakistan, and Sri Lanka; not Pakistan-only",
        "- Split: publisher states speaker-disjoint train/dev/test",
        "- License: CC0-1.0; do not identify speakers or rehost the dataset",
        "- Acquisition: blocked until the selected manifest is frozen",
        "",
        "## Rights and checkpoint exposure",
        "",
        "| Corpus | License | Local evaluation | Distribution/access limits |",
        "| --- | --- | --- | --- |",
    ]
    for source, details in sorted(rights_rows.items()):
        rights = details.get("rights", {})
        license_name = details.get("declared_license") or rights.get(
            "dataset_declared_license", rights.get("license_scope", "PER_RECORDING_PERMISSION")
        )
        local_use = rights.get("local_asr_evaluation", "PENDING")
        distribution = (
            rights.get("media_redistribution")
            or rights.get("redistribution")
            or rights.get("public_distribution")
            or rights.get("rehosting", "NOT_DOCUMENTED")
        )
        source_url = details.get("source_url")
        label = f"[{source}]({source_url})" if source_url else source
        lines.append(f"| {label} | {license_name} | {local_use} | {distribution} |")
    lines += [
        "",
        "The two Mozilla Common Voice sources prohibit speaker identification and rehosting;",
        "CC0 does not override those publisher restrictions. UrduSpeech source-media rights and",
        "Pashto consent/redistribution review remain open.",
        "",
        "All four pinned checkpoint revisions are recorded. Unknown exposure remains `UNKNOWN`;",
        "it is never converted to clear. BuzzASR remains related to Common Voice and its Sindhi",
        "public-corpus results remain reference-only.",
        "",
        "## Sindhi holdout protocol",
        "",
        "The collection protocol is approved and fail-closed, but data remains `PENDING` at",
        "0/100 recordings and 0/10 speakers. Model evaluation remains `NOT_RUN`.",
        "",
        "## Blocking items",
        "",
    ]
    lines.extend(f"- {blocker}" for blocker in report["blockers"])
    lines += [
        "",
        "The gate may become `AUDIO_ACQUISITION_READY` only when every Boolean criterion in the",
        "JSON gate is true. Until then, do not download audio or execute a model.",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def audit_readiness(root: Path, fetch: Fetch = fetch_url) -> dict[str, Any]:
    report = build_readiness(root, fetch)
    json_path = root / READINESS_JSON_PATH
    markdown_path = root / READINESS_MARKDOWN_PATH
    put_json(json_path, report)
    put_immutable(markdown_path, render_markdown(report))
    gate = {
        "registry_version": "eval-voice-corpora-v2-readiness-gate-v1",
        "protocol_id": PROTOCOL_ID,
        "amendment_id": AMENDMENT_ID,
        "status": report["status"],
        "target_status": report["target_status"],
        "audio_dataset_status": "NOT_FROZEN",
        "model_results": "NOT_RUN",
        "criteria": report["gate_criteria"],
        "report_sha256": file_sha256(json_path),
        "markdown_sha256": file_sha256(markdown_path),
    }
    put_json(root / READINESS_GATE_PATH, gate)
    return verify_readiness(root)


def verify_readiness(root: Path) -> dict[str, Any]:
    protocol = verify_protocol(root)
    report = read_canonical_json(root / READINESS_JSON_PATH)
    gate = read_canonical_json(root / READINESS_GATE_PATH)
    if (
        report.get("protocol_registry_checksum") != protocol["registry_checksum"]
        or report.get("readiness_checksum")
        != record_checksum(
            {key: value for key, value in report.items() if key != "readiness_checksum"}
        )
        or (root / READINESS_MARKDOWN_PATH).read_bytes() != render_markdown(report)
        or gate.get("report_sha256") != file_sha256(root / READINESS_JSON_PATH)
        or gate.get("markdown_sha256") != file_sha256(root / READINESS_MARKDOWN_PATH)
        or gate.get("status") != "BLOCKED"
        or gate.get("target_status") != "AUDIO_ACQUISITION_READY"
        or gate.get("criteria") != report.get("gate_criteria")
        or all(gate["criteria"].values())
        or gate.get("audio_dataset_status") != "NOT_FROZEN"
        or gate.get("model_results") != "NOT_RUN"
    ):
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    return gate


def status(root: Path) -> dict[str, Any]:
    protocol = verify_protocol(root)
    result: dict[str, Any] = {
        "protocol_id": PROTOCOL_ID,
        "amendment_id": AMENDMENT_ID,
        "protocol_status": protocol["status"],
        "readiness": "NOT_AUDITED",
        "target_status": "AUDIO_ACQUISITION_READY",
        "audio_dataset_status": "NOT_FROZEN",
        "model_results": "NOT_RUN",
    }
    if (root / READINESS_GATE_PATH).exists():
        result["readiness"] = verify_readiness(root)["status"]
    return result
