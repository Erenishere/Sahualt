from pathlib import Path

import pytest

from sahulat_voice.corpora_v2_readiness.analysis import classify_difference
from sahulat_voice.corpora_v2_readiness.protocol import load_config, verify_protocol

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "transcription,ground_truth,expected",
    [
        ("e\u0301", "é", "UNICODE_NORMALIZATION_ONLY"),
        ("Hello,   world!", "hello world", "PUNCTUATION_OR_WHITESPACE_ONLY"),
        ("hello", "سلام", "SCRIPT_PROFILE_CHANGE"),
        ("one two", "one new two", "MISSING_OR_ADDED_WORDS"),
        ("color shoe", "colour shoe", "SPELLING_OR_TOKEN_SUBSTITUTION"),
        ("one two", "different phrase here", "SEMANTIC_REVIEW_REQUIRED"),
    ],
)
def test_difference_classifier(transcription, ground_truth, expected):
    assert classify_difference(transcription, ground_truth) == expected


def test_difference_classifier_rejects_equal_strings():
    with pytest.raises(ValueError):
        classify_difference("same", "same")


def test_checked_in_readiness_protocol_and_source_pin():
    config = load_config(ROOT)
    english = config["sources"]["south_asian_english"]
    assert english["dataset_id"] == "cmrt70sar001umm07jwxzhw89"
    assert english["test_clips"] == 3864
    assert english["test_speakers"] == 81
    assert english["accent_scope"].endswith("not_pakistan_only")
    assert english["rights"]["rehosting"] == "FORBIDDEN"
    assert config["sources"]["urduspeech"]["rights"]["local_asr_evaluation"].startswith("PENDING_")
    assert config["sources"]["pashto_audio_visual"]["rights"]["license_scope"] == (
        "PUBLISHER_STATES_CC0_1_0"
    )
    assert config["checkpoint_exposure"]["unknown_means_clear"] is False
    gate = verify_protocol(ROOT)
    assert gate["status"] == "FROZEN_ACQUISITION_READINESS_PROTOCOL"
    assert gate["model_results"] == "NOT_RUN"
