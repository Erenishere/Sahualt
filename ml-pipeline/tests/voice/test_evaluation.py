import hashlib
import json

import pytest

from sahulat_voice.cli import main
from sahulat_voice.errors import ErrorCode, VoiceError
from sahulat_voice.evaluation import (
    EVALUATION_SCHEMA,
    load_evaluation_input,
    resolve_audio_path,
    transcript_error_counts,
)


@pytest.fixture
def manifest(tmp_path, wav_file):
    # These synthetic metadata/reference strings are schema-test data, never human evidence.
    path = tmp_path / "synthetic-evaluation.json"
    record = {
        "sample_id": "test_1",
        "language": "en",
        "audio_path": wav_file.name,
        "audio_sha256": hashlib.sha256(wav_file.read_bytes()).hexdigest(),
        "reference_text": "Synthetic reference",
        "reference_author": "test-author",
        "reference_source": "human",
        "source": "human_recording",
        "use_permission_confirmed": True,
    }
    path.write_text(
        json.dumps({"schema_version": EVALUATION_SCHEMA, "samples": [record]}), encoding="utf-8"
    )
    return path


def test_valid_human_input_schema_verifies_audio(manifest, tmp_path):
    evidence = load_evaluation_input(manifest, tmp_path)
    assert len(evidence.samples) == 1
    assert evidence.samples[0].reference_text == "Synthetic reference"
    assert evidence.summary()["evaluation_results"] == "NOT_RUN"


def test_empty_neutral_template_pending(tmp_path, capsys):
    path = tmp_path / "empty.json"
    path.write_text(json.dumps({"schema_version": EVALUATION_SCHEMA, "samples": []}))
    assert (
        main(["validate-evaluation-input", "--manifest", str(path), "--audio-root", str(tmp_path)])
        == 0
    )
    summary = json.loads(capsys.readouterr().out)
    assert summary["human_evaluation_data"] == "PENDING"
    assert summary["sample_count"] == 0
    assert all(count == 0 for count in summary["language_counts"].values())


@pytest.mark.parametrize(
    "field, value",
    [
        ("language", "auto"),
        ("language", ["en"]),
        ("sample_id", ""),
        ("audio_sha256", "0" * 64),
        ("reference_text", " "),
        ("reference_text", "\ud800"),
        ("reference_author", ""),
        ("reference_source", "llm"),
        ("source", "synthetic"),
        ("use_permission_confirmed", 1),
        ("score", 0.95),
        ("rank", 1),
        ("product_id", "fake"),
    ],
)
def test_bad_metadata_or_ranking_fields_rejected(manifest, tmp_path, field, value):
    document = json.loads(manifest.read_bytes())
    document["samples"][0][field] = value
    manifest.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(VoiceError):
        load_evaluation_input(manifest, tmp_path)


@pytest.mark.parametrize(
    "reference",
    [
        "../escape.wav",
        "/absolute.wav",
        "C:/private.wav",
        "C:\\private.wav",
        "dir/../file.wav",
        "./file.wav",
        "file.mp3",
        "dir//file.wav",
        "file.wav:stream",
    ],
)
def test_path_leakage_and_escape_rejected(tmp_path, reference):
    with pytest.raises(VoiceError):
        resolve_audio_path(tmp_path, reference)


@pytest.mark.parametrize("variant", ["id", "audio"])
def test_duplicate_ids_or_recordings_rejected(manifest, tmp_path, variant):
    document = json.loads(manifest.read_bytes())
    copied = dict(document["samples"][0])
    if variant == "audio":
        copied["sample_id"] = "test_2"
    document["samples"].append(copied)
    manifest.write_text(json.dumps(document))
    with pytest.raises(VoiceError) as caught:
        load_evaluation_input(manifest, tmp_path)
    assert caught.value.code == ErrorCode.INVALID_MANIFEST


@pytest.mark.parametrize(
    "text",
    [
        "",
        "not json",
        "[]",
        '{"schema_version":"unsupported","samples":[]}',
        '{"schema_version":"voice-evaluation-input-v1","samples":{}}',
        '{"samples":[],"samples":[]}',
    ],
)
def test_malformed_or_unsupported_manifest(tmp_path, text):
    path = tmp_path / "input.json"
    path.write_text(text)
    with pytest.raises(VoiceError):
        load_evaluation_input(path, tmp_path)


def test_manifest_serialization_is_deterministic(manifest, tmp_path):
    first = load_evaluation_input(manifest, tmp_path)
    document = json.loads(manifest.read_bytes())
    manifest.write_text(json.dumps(document, indent=4, sort_keys=True))
    second = load_evaluation_input(manifest, tmp_path)
    assert first.manifest_sha256 == second.manifest_sha256


def test_audio_tamper_detected(manifest, wav_file, tmp_path):
    payload = bytearray(wav_file.read_bytes())
    payload[-1] = 1
    wav_file.write_bytes(payload)
    with pytest.raises(VoiceError) as caught:
        load_evaluation_input(manifest, tmp_path)
    assert caught.value.code == ErrorCode.CHECKSUM_MISMATCH


@pytest.mark.parametrize(
    "reference, hypothesis, expected",
    [
        ("test speech", "test speech", 0),
        ("test speech", "test", 1),
        ("test", "test extra words", 2),
        ("café", "cafe\u0301", 0),
        ("اردو", "اردو", 0),
        ("سنڌي", "سنڌي", 0),
        ("پښتو", "پښتو", 0),
    ],
)
def test_wer_cer_scaffold_counts_only_synthetic_test_text(reference, hypothesis, expected):
    counts = transcript_error_counts(reference, hypothesis)
    assert counts["word_errors"] == expected
    if expected == 0:
        assert counts["character_errors"] == 0


def test_wer_not_clamped_and_empty_reference_not_fabricated():
    assert transcript_error_counts("test", "test extra words")["wer"] == 2.0
    with pytest.raises(VoiceError):
        transcript_error_counts("", "test")
