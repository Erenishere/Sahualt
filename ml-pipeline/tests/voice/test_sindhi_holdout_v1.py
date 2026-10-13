import copy

import pytest

from sahulat_voice.alternatives import sindhi_holdout_v1 as holdout
from sahulat_voice.errors import VoiceError


def pending_document():
    utterances = [
        {
            "utterance_id": f"UTT{index:03d}",
            "text": f"سنڌي جملو {index}",
            "domain": "commerce" if index < 30 else "everyday",
            "length_category": ("short", "medium", "long")[index % 3],
            "author": "human-author",
            "reviewer": "human-reviewer",
        }
        for index in range(50)
    ]
    speakers = [
        {
            "speaker_id": f"SPK{index:03d}",
            "speaker_permission_confirmed": True,
            "speaker_public_corpus_attestation": {
                "common_voice": index == 0,
                "fleurs": False,
                "buzzasr_related": False,
                "other_public_sindhi_asr": False,
            },
        }
        for index in range(10)
    ]
    return {
        "schema_version": holdout.VERSION,
        "utterances": utterances,
        "speakers": speakers,
        "recordings": [],
        "assignment": holdout.build_assignment(
            [item["utterance_id"] for item in utterances],
            [item["speaker_id"] for item in speakers],
        ),
    }


def test_empty_input_is_pending_and_cannot_freeze(tmp_path):
    document = {
        "schema_version": holdout.VERSION,
        "utterances": [],
        "speakers": [],
        "recordings": [],
        "assignment": [],
    }
    assert holdout.validate(document, tmp_path)["complete"] is False


def test_public_corpus_attestation_keys_are_not_treated_as_recording_sources(tmp_path):
    validated = holdout.validate(pending_document(), tmp_path)
    assert validated["complete"] is False
    assert validated["speakers"][0]["speaker_public_corpus_attestation"]["common_voice"] is True


def test_forbidden_recording_source_is_rejected_before_audio_read(tmp_path):
    document = pending_document()
    speaker = document["speakers"][0]
    utterance = document["utterances"][0]
    document["recordings"] = [
        {
            "schema_version": holdout.VERSION,
            "recording_id": "REC000",
            "utterance_id": utterance["utterance_id"],
            "speaker_id": speaker["speaker_id"],
            "language": "sd",
            "domain": utterance["domain"],
            "audio_path": "recording.wav",
            "audio_sha256": "0" * 64,
            "reference_text": utterance["text"],
            "reference_source": "human",
            "reference_reviewer": "human-reviewer",
            "speaker_permission_confirmed": True,
            "speaker_public_corpus_attestation": copy.deepcopy(
                speaker["speaker_public_corpus_attestation"]
            ),
            "recording_source": "common_voice",
            "preparation_version": "sindhi-holdout-preparation-v1",
        }
    ]
    with pytest.raises(VoiceError):
        holdout.validate(document, tmp_path)
