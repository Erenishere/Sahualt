import hashlib
import tempfile
from pathlib import Path

import pytest

from sahulat_voice.benchmark.io import canonical_bytes, record_checksum
from sahulat_voice.corpora_v2_manifest_freeze.freeze import (
    _read_frozen_json,
    _verify_hash_refs,
    require_acquisition_ready,
    select_metadata_rows,
)
from sahulat_voice.errors import ErrorCode, VoiceError


def _row(
    sample_id: str,
    audio_sha256: str,
    *,
    subset: str = "standard_urdu",
    exact: bool = True,
) -> dict[str, object]:
    return {
        "sample_id": sample_id,
        "source_sample_id": f"source-{sample_id}",
        "subset": subset,
        "language": "ur" if subset == "standard_urdu" else "ur-en",
        "speaker_id": "SPEAKER_001",
        "metadata_path": f"benchmark/{subset}/clean_transcription.jsonl",
        "line_number": 1,
        "audio_path": f"benchmark/{subset}/audio/{sample_id}.wav",
        "audio_sha256": audio_sha256,
        "duration_seconds": 2.0,
        "duration_group": "short",
        "category": "VLOG",
        "transcript_evidence": {
            "Transcription": {"sha256": "a" * 64, "codepoints": 4},
            "ground_truth": {"sha256": "a" * 64 if exact else "b" * 64, "codepoints": 4},
        },
        "discrepancy_flags": {
            "exact_field_match": exact,
            "category": None if exact else "SPELLING_OR_TOKEN_SUBSTITUTION",
            "human_adjudication_required": not exact,
            "semantic_review_required": not exact,
            "authoritative_reference": "BOTH_SOURCE_FIELDS_IDENTICAL_NOT_INDEPENDENTLY_ADJUDICATED"
            if exact
            else "PENDING_HUMAN_ADJUDICATION",
        },
    }


def _contracts(target: int = 1) -> dict[str, dict[str, object]]:
    return {
        "standard_urdu": {"sample_target": target},
        "code_switched": {"sample_target": 0},
        "pakistani_english": {"sample_target": 0},
    }


def test_selection_is_deterministic_and_preserves_source_identifiers() -> None:
    rows = [_row("eval-b", "b" * 64), _row("eval-a", "a" * 64)]
    rows[0]["source_sample_id"] = rows[1]["source_sample_id"] = "repeated-source-id"
    first = select_metadata_rows(rows, _contracts(target=2), 20261012, 30)
    second = select_metadata_rows(rows, _contracts(target=2), 20261012, 30)

    assert first == second
    selected, decisions = first
    assert {row["sample_id"] for row in selected["standard_urdu"]} == {"eval-a", "eval-b"}
    assert {
        entry["source_sample_id"]
        for entry in decisions["standard_urdu"]
        if entry["selection_decision"] == "SELECTED"
    } == {"repeated-source-id"}
    assert all(entry["speaker_label"] == "SPEAKER_001" for entry in decisions["standard_urdu"])
    assert all(
        entry["speaker_identity_status"] == "UNVERIFIED_PUBLISHED_LABEL"
        for entry in decisions["standard_urdu"]
    )


def test_duplicates_and_unadjudicated_transcripts_are_excluded() -> None:
    rows = [
        _row("dup-a", "d" * 64),
        _row("dup-b", "d" * 64),
        _row("mismatch", "m" * 64, exact=False),
        _row("unique", "u" * 64),
    ]
    selected, decisions = select_metadata_rows(rows, _contracts(target=1), 20261012, 30)

    assert [row["sample_id"] for row in selected["standard_urdu"]] == ["unique"]
    by_id = {row["evaluation_record_id"]: row for row in decisions["standard_urdu"]}
    assert "DUPLICATE_PUBLISHER_AUDIO_SHA256" in by_id["dup-a"]["exclusion_reasons"]
    assert "DUPLICATE_PUBLISHER_AUDIO_SHA256" in by_id["dup-b"]["exclusion_reasons"]
    assert "TRANSCRIPT_MISMATCH_UNADJUDICATED" in by_id["mismatch"]["exclusion_reasons"]
    assert by_id["mismatch"]["discrepancy_flags"]["human_adjudication_required"] is True


def test_checksum_drift_is_rejected() -> None:
    with tempfile.TemporaryDirectory(prefix=".pytest_mf_checksum_", dir=Path.cwd()) as temporary:
        root = Path(temporary)
        path = root / "manifest.json"
        record = {"items": ["pinned"], "checksum": record_checksum({"items": ["pinned"]})}
        path.write_bytes(canonical_bytes(record))
        references = {
            "manifest": {
                "path": "manifest.json",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        }
        _verify_hash_refs(root, references)

        path.write_bytes(canonical_bytes({"items": ["drifted"]}))
        with pytest.raises(VoiceError) as error:
            _verify_hash_refs(root, references)
        assert error.value.code is ErrorCode.CHECKSUM_MISMATCH


def test_large_frozen_json_uses_bounded_canonical_reader() -> None:
    with tempfile.TemporaryDirectory(
        prefix=".pytest_mf_large_ledger_", dir=Path.cwd()
    ) as temporary:
        path = Path(temporary) / "ledger.json"
        record = {"entry": "x" * (2 * 1024 * 1024 + 1)}
        path.write_bytes(canonical_bytes(record))
        assert _read_frozen_json(path) == record


def test_acquisition_gate_rejects_unresolved_rights_and_non_frozen_source() -> None:
    source_status = {
        "source_status": "BLOCKED",
        "acquisition_status": "BLOCKED",
        "evaluation_independence": "NOT_VERIFIED",
        "rights": {"rights": {"local_asr_evaluation": "PENDING_SOURCE_MEDIA_RIGHTS_REVIEW"}},
    }

    with pytest.raises(VoiceError) as error:
        require_acquisition_ready(source_status, manifest_frozen=False)
    assert error.value.code is ErrorCode.INVALID_MANIFEST

    explicitly_allowed = {
        "source_status": "ACTIVE",
        "acquisition_status": "ALLOWED",
        "evaluation_independence": "VERIFIED",
        "rights": {"rights": {"local_asr_evaluation": "ALLOWED"}},
    }
    with pytest.raises(VoiceError) as error:
        require_acquisition_ready(explicitly_allowed, manifest_frozen=False)
    assert error.value.code is ErrorCode.INVALID_MANIFEST
