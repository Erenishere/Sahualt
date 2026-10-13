import hashlib
import json
from pathlib import Path

import pytest

from sahulat_voice.corpora_v2.audit import (
    _git_blob_id,
    inventory_summary,
    parse_clean_metadata,
    parse_inventory,
    selection_preview,
)
from sahulat_voice.corpora_v2.registry import load_registry, verify_protocol
from sahulat_voice.errors import VoiceError

REPOSITORY = Path(__file__).resolve().parents[2]


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def test_checked_in_protocol_and_registry():
    registry = load_registry(REPOSITORY)
    assert registry["protocol"]["no_training_or_tuning"] is True
    assert registry["sources"]["pashto_audio_visual"]["status"] == "QUARANTINED_AUDIT_ONLY"
    assert verify_protocol(REPOSITORY)["model_results"] == "NOT_RUN"


def test_inventory_accepts_pinned_lfs_audio_and_git_metadata():
    document = {
        "siblings": [
            {
                "rfilename": "benchmark/US-benchmark-Std/short/NEWS/audio/a.WAV",
                "size": 4,
                "blobId": "a" * 40,
                "lfs": {"sha256": "b" * 64, "size": 4},
            },
            {
                "rfilename": "benchmark/US-benchmark-Std/short/NEWS/clean_transcription.jsonl",
                "size": 3,
                "blobId": "c" * 40,
                "lfs": None,
            },
        ]
    }
    inventory = parse_inventory(canonical(document), "benchmark")
    summary = inventory_summary(inventory)
    assert summary["audio_file_count"] == 1
    assert summary["metadata_file_count"] == 1
    assert summary["byte_count"] == 7


def test_inventory_rejects_traversal():
    document = {
        "siblings": [
            {"rfilename": "benchmark/../secret", "size": 1, "blobId": "a" * 40, "lfs": None}
        ]
    }
    with pytest.raises(VoiceError):
        parse_inventory(canonical(document), "benchmark")


def test_clean_metadata_maps_reference_without_storing_text():
    metadata_path = "benchmark/US-benchmark-Std/short/NEWS/clean_transcription.jsonl"
    audio_path = "benchmark/US-benchmark-Std/short/NEWS/audio/SPEAKER_001_NEWS_0001.WAV"
    row = {
        "Speaker_id": "SPEAKER_001",
        "Audio_category": "NEWS",
        "Audio_Clip": "SPEAKER_001_NEWS_0001.WAV",
        "audio_id": "NEWS_0001.WAV",
        "Duration_seconds": "4.5",
        "Word_count": "2",
        "Character_count": "8",
        "Transcription": "اصل متن",
        "ground_truth": "اصل متن",
    }
    assets = {
        audio_path: {
            "path": audio_path,
            "size": 10,
            "blob_id": "a" * 40,
            "lfs_sha256": "b" * 64,
        }
    }
    records = parse_clean_metadata(canonical(row) + b"\n", metadata_path, "standard_urdu", assets)
    assert records[0]["reference_sha256"] == hashlib.sha256("اصل متن".encode()).hexdigest()
    assert records[0]["duration_seconds"] == 4.5
    assert "ground_truth" not in records[0]


def test_selection_preview_excludes_long_and_duplicate_audio():
    def record(index, duration, digest):
        return {
            "sample_id": f"s{index}",
            "duration_group": "short",
            "category": "NEWS",
            "speaker_id": f"SPEAKER_{index:03d}",
            "duration_seconds": duration,
            "audio_sha256": digest,
        }

    records = [
        record(1, 4, "a" * 64),
        record(2, 4, "a" * 64),
        record(3, 31, "b" * 64),
        record(4, 5, "c" * 64),
    ]
    preview = selection_preview(records, "standard_urdu", 2, 20261012)
    assert preview["selected_count"] == 1
    assert preview["duplicate_audio_excluded_count"] == 2
    assert preview["target_met"] is False


def test_git_blob_identity_is_content_addressed():
    assert _git_blob_id(b"hello") == "b6fc4c620b67d95f953a5c1c1230aaab5db5a1b0"
