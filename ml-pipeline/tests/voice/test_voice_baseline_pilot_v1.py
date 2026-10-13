import copy
import hashlib
import io
import json
import runpy
import wave
from datetime import date, timedelta
from pathlib import Path

import pytest

from sahulat_voice import pilot_v1 as pilot
from sahulat_voice.errors import ErrorCode, VoiceError
from sahulat_voice.transcript import canonical_bytes

ROOT = Path(__file__).resolve().parents[2]


def wav_payload(seed: int) -> bytes:
    stream = io.BytesIO()
    with wave.open(stream, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(seed.to_bytes(2, "little", signed=True) * 1600)
    return stream.getvalue()


def bundle(tmp_path, count=1, group="ur", native=True):
    audio_root = tmp_path / "audio"
    evidence_root = tmp_path / "consent-evidence"
    audio_root.mkdir(exist_ok=True)
    evidence_root.mkdir(exist_ok=True)
    recordings = []
    speakers = sorted({f"SPK_{index % 5 + 1:03}" for index in range(count)})
    consents = []
    for sid in speakers:
        evidence = evidence_root / f"{sid}.pdf"
        evidence.write_bytes(f"test-only consent evidence:{sid}".encode())
        consents.append(
            {
                "speaker_id": sid,
                "status": "active",
                "signed_at": "2026-10-01",
                "retention_until": "2099-10-01",
                "adult_participant_confirmed": True,
                "form_version": "VOICE-BASELINE-PILOT-CONSENT-V1",
                "allowed_groups": [group],
                "native_language_groups": [group] if native else [],
                "permissions": {
                    "private_audio_storage": True,
                    "local_asr_processing": True,
                    "aggregate_research_reporting": True,
                    "deidentified_transcript_examples": True,
                    "public_audio_release": False,
                },
                "withdrawn": False,
                "consent_evidence_path": evidence.name,
                "consent_evidence_sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
                "reviewer_id": "CONSENT_REVIEWER",
                "reviewed_at": "2026-10-01",
            }
        )
    for index in range(count):
        sample_id = f"{group.upper()}_{index + 1:03}"
        speaker_id = f"SPK_{index % 5 + 1:03}"
        audio_path = audio_root / f"{sample_id}.wav"
        audio_path.write_bytes(wav_payload(index + 1))
        recordings.append(
            {
                "sample_id": sample_id,
                "speaker_id": speaker_id,
                "language_group": group,
                "audio_path": audio_path.name,
                "audio_sha256": hashlib.sha256(audio_path.read_bytes()).hexdigest(),
                "reference_text": "Sample spoken words",
                "reference_script": "latin",
                "reference_status": "human_verified",
                "reference_transcriber_id": "TRANSCRIBER",
                "reference_reviewer_id": "REFERENCE_REVIEWER",
                "reference_reviewed_at": "2026-10-03",
                "recording_source": "fresh_human_recording",
                "recording_source_review_status": "human_verified",
                "recording_reviewer_id": "COLLECTION_REVIEWER",
                "recording_reviewed_at": "2026-10-02",
                "tts_generated": False,
                "recorded_at": "2026-10-02",
                "roman_urdu_reference": None,
                "roman_urdu_reference_status": None,
                "roman_urdu_reference_reviewer_id": None,
                "roman_urdu_reference_reviewed_at": None,
                "commerce_annotation": None,
            }
        )
    return (
        {
            "schema_version": pilot.INPUT_SCHEMA,
            "source_id": pilot.SOURCE_ID,
            "recordings": recordings,
        },
        {
            "schema_version": pilot.CONSENT_SCHEMA,
            "source_id": pilot.SOURCE_ID,
            "consents": consents,
        },
        audio_root,
        evidence_root,
    )


def test_empty_private_workspace_is_pending_not_evaluation(tmp_path):
    result = pilot.validate_bundle(
        {"schema_version": pilot.INPUT_SCHEMA, "source_id": pilot.SOURCE_ID, "recordings": []},
        {"schema_version": pilot.CONSENT_SCHEMA, "source_id": pilot.SOURCE_ID, "consents": []},
        tmp_path,
        tmp_path,
    )
    assert result["status"] == "PENDING_RECORDINGS"
    assert all(value["selected_recordings"] == 0 for value in result["counts"].values())


def test_cli_validate_accepts_empty_workspace_as_pending(tmp_path, capsys):
    cli = runpy.run_path(str(ROOT / "scripts/voice_baseline_pilot_v1.py"))
    workspace = tmp_path / "private-workspace"

    assert cli["main"](["validate", "--workspace", str(workspace)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "PENDING_RECORDINGS"
    assert sum(group["selected_recordings"] for group in result["counts"].values()) == 0


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_consent",
        "withdrawn",
        "no_local_asr_permission",
        "tts_generated",
        "third_party_source",
        "unreviewed_reference",
        "same_transcriber_and_reviewer",
    ],
)
def test_unconsented_tts_third_party_or_unreviewed_recording_is_rejected(tmp_path, mutation):
    document, consent, audio_root, evidence_root = bundle(tmp_path)
    if mutation == "missing_consent":
        consent["consents"] = []
    elif mutation == "withdrawn":
        consent["consents"][0]["withdrawn"] = True
    elif mutation == "no_local_asr_permission":
        consent["consents"][0]["permissions"]["local_asr_processing"] = False
    elif mutation == "tts_generated":
        document["recordings"][0]["tts_generated"] = True
    elif mutation == "third_party_source":
        document["recordings"][0]["recording_source"] = "common_voice"
    elif mutation == "unreviewed_reference":
        document["recordings"][0]["reference_status"] = "pending"
    else:
        document["recordings"][0]["reference_transcriber_id"] = "REFERENCE_REVIEWER"
    with pytest.raises(VoiceError):
        pilot.validate_bundle(document, consent, audio_root, evidence_root)


def test_evidence_audio_checksums_and_reference_preservation(tmp_path):
    document, consent, audio_root, evidence_root = bundle(tmp_path)
    document["recordings"][0]["reference_text"] = "  Sample spoken words  "
    validated = pilot.validate_bundle(document, consent, audio_root, evidence_root)
    assert validated["eligible_recordings"][0]["reference_text"] == "  Sample spoken words  "
    consent["consents"][0]["consent_evidence_sha256"] = "0" * 64
    with pytest.raises(VoiceError) as caught:
        pilot.validate_bundle(document, consent, audio_root, evidence_root)
    assert caught.value.code == ErrorCode.CHECKSUM_MISMATCH


def test_duplicate_audio_is_rejected(tmp_path):
    document, consent, audio_root, evidence_root = bundle(tmp_path, count=2)
    document["recordings"][1]["audio_sha256"] = document["recordings"][0]["audio_sha256"]
    with pytest.raises(VoiceError) as caught:
        pilot.validate_bundle(document, consent, audio_root, evidence_root)
    assert caught.value.code == ErrorCode.INVALID_MANIFEST


def test_expired_consent_is_not_eligible_for_freeze(tmp_path):
    document, consent, audio_root, evidence_root = bundle(tmp_path)
    consent_record = consent["consents"][0]
    consent_record["signed_at"] = "2020-01-01"
    consent_record["reviewed_at"] = "2020-01-01"
    consent_record["retention_until"] = (date.today() - timedelta(days=1)).isoformat()
    recording = document["recordings"][0]
    recording["recorded_at"] = "2020-01-02"
    recording["recording_reviewed_at"] = "2020-01-02"
    recording["reference_reviewed_at"] = "2020-01-03"

    with pytest.raises(VoiceError):
        pilot.validate_bundle(document, consent, audio_root, evidence_root)


def test_selection_is_deterministic_balanced_and_caps_at_30(tmp_path):
    document, consent, audio_root, evidence_root = bundle(tmp_path, count=35)
    first = pilot.validate_bundle(document, consent, audio_root, evidence_root)
    shuffled = copy.deepcopy(document)
    shuffled["recordings"].reverse()
    second = pilot.validate_bundle(shuffled, consent, audio_root, evidence_root)
    assert [row["sample_id"] for row in first["selected_recordings"]] == [
        row["sample_id"] for row in second["selected_recordings"]
    ]
    assert len(first["selected_recordings"]) == 30
    assert {
        row["speaker_id"]: sum(
            selected["speaker_id"] == row["speaker_id"] for selected in first["selected_recordings"]
        )
        for row in first["selected_recordings"]
    } == {f"SPK_{index:03}": 6 for index in range(1, 6)}
    assert (
        sum(row["decision"] == "NOT_SELECTED_TARGET_CAP" for row in first["selection_audit"]) == 5
    )


def test_freeze_is_content_addressed_and_detects_audio_drift(tmp_path):
    document, consent, audio_root, evidence_root = bundle(tmp_path)
    workspace = tmp_path / "private-workspace"
    result = pilot.freeze_bundle(ROOT, document, consent, audio_root, evidence_root, workspace)
    assert result["status"] == "FROZEN_PILOT"
    frozen_dir = Path(result["manifest_path"]).parent
    assert pilot.verify_frozen(frozen_dir, ROOT)["status"] == "FROZEN_VERIFIED"
    frozen_audio = frozen_dir / "audio" / "UR_001.wav"
    payload = bytearray(frozen_audio.read_bytes())
    payload[-1] ^= 1
    frozen_audio.write_bytes(payload)
    with pytest.raises(VoiceError):
        pilot.verify_frozen(frozen_dir, ROOT)


def test_consent_registry_drift_blocks_before_adapter_creation(tmp_path):
    document, consent, audio_root, evidence_root = bundle(tmp_path)
    workspace = tmp_path / "private-workspace"
    workspace.mkdir()
    (workspace / "consent-evidence").mkdir()
    for item in evidence_root.iterdir():
        (workspace / "consent-evidence" / item.name).write_bytes(item.read_bytes())
    (workspace / "consent_registry.json").write_bytes(canonical_bytes(consent))
    result = pilot.freeze_bundle(ROOT, document, consent, audio_root, evidence_root, workspace)
    manifest_dir = Path(result["manifest_path"]).parent
    consent["consents"][0]["withdrawn"] = True
    (workspace / "consent_registry.json").write_bytes(canonical_bytes(consent))

    def forbidden_factory(*_args):
        raise AssertionError("models must not be initialized after consent drift")

    with pytest.raises(VoiceError) as caught:
        pilot.run_evaluation(ROOT, manifest_dir, forbidden_factory, workspace)
    assert caught.value.code == ErrorCode.INVALID_MANIFEST


def test_script_aware_normalization_and_price_metrics():
    assert pilot.score_text("۵٬۰۰۰ روپیاں", "5,000 روپیاں!", "ur")["wer"] == 0
    assert pilot.detect_script("Mujhe کالا kurta") == "mixed"
    assert pilot._number_values("under 5,000 rupees") == {"5000"}


def test_human_reviewed_commerce_annotations_score_transcription_cues(tmp_path):
    document, consent, audio_root, evidence_root = bundle(tmp_path)
    sample = document["recordings"][0]
    sample["reference_text"] = "Show me Khaadi under 5,000 rupees"
    sample["commerce_annotation"] = {
        "intent_label": "price_check",
        "intent_cues": ["Show me"],
        "brand_names": ["Khaadi"],
        "prices": [
            {
                "amount_major": "5000",
                "currency": "PKR",
                "spoken_forms": ["5,000 rupees"],
            }
        ],
        "reviewer_id": "COMMERCE_REVIEWER",
        "reviewed_at": "2026-10-04",
    }
    validated = pilot.validate_bundle(document, consent, audio_root, evidence_root)
    sample = validated["selected_recordings"]
    summary = pilot._commerce_counts(
        sample, {"UR_001": "Show me Khaadi under Rs. 5000 rupees"}, "ur"
    )
    assert summary["intent_cue_preservation_rate"] == 1
    assert summary["brand_exact_preservation_rate"] == 1
    assert summary["price_amount_recognition_rate"] == 1
    assert summary["intent_classification_accuracy"] is None


def test_error_examples_require_post_run_permission_and_distinct_review(tmp_path):
    manifest_sha = "a" * 64
    result = {
        "execution_date": "2026-10-12",
        "manifest_sha256": manifest_sha,
        "model_results": {
            "whisper:ur": {
                "model_id": "whisper-large-v3-turbo",
                "records": [
                    {
                        "sample_id": "UR_001",
                        "status": "SUCCESS",
                        "scoring": {"word_errors": 1, "character_errors": 2},
                        "error_example_permission": True,
                        "reference_transcriber_id": "TRANSCRIBER",
                        "reference_reviewer_id": "ANNOTATOR",
                        "recording_reviewer_id": "COLLECTOR",
                    }
                ],
            }
        },
    }
    review = pilot.error_review_template(manifest_sha)
    review["reviews"] = [
        {
            "model_id": "whisper-large-v3-turbo",
            "sample_id": "UR_001",
            "decision": "APPROVED",
            "reviewer_id": "PRIVACY_REVIEWER",
            "reviewed_at": "2026-10-13",
            "deidentification_confirmed": True,
        }
    ]
    _, counts = pilot.validate_error_reviews(result, review)
    assert counts == {"approved": 1, "rejected": 0, "unreviewed": 0}
    review["reviews"][0]["reviewer_id"] = "ANNOTATOR"
    with pytest.raises(VoiceError):
        pilot.validate_error_reviews(result, review)
