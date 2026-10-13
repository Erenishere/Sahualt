import ast
import hashlib
import json
import struct
from pathlib import Path

import numpy as np
import pytest

from sahulat_voice.adapters import STTAdapter, create_adapter
from sahulat_voice.audio import MAX_AUDIO_BYTES, ValidatedAudio, read_audio, validate_audio
from sahulat_voice.cli import main
from sahulat_voice.contracts import MODEL_SPECS, Language, RuntimeSettings, parse_language
from sahulat_voice.errors import ErrorCode, VoiceError
from sahulat_voice.service import TranscriptionService
from sahulat_voice.transcript import build_transcript, canonical_bytes, normalize_transcript

from .conftest import synthetic_wav


class SyntheticAdapter(STTAdapter):
    """Test double only; its text must never be reported as model output."""

    spec = MODEL_SPECS["whisper"]

    def __init__(self, text: str = "  Test\n transcript.  ") -> None:
        self.text = text
        self.calls: list[Language] = []

    def transcribe(self, audio: ValidatedAudio, language: Language) -> str:
        self.calls.append(language)
        return self.text


def test_pcm_signal_is_bounded_detached_and_content_hashed(signal_bytes):
    audio = validate_audio(signal_bytes)
    samples = audio.samples()
    assert samples.dtype == np.float32
    assert np.isfinite(samples).all()
    assert np.abs(samples).max() <= 1.0
    assert audio.duration_seconds == 0.1
    assert audio.sha256 == hashlib.sha256(signal_bytes).hexdigest()
    samples[:] = 0
    assert np.any(audio.samples())


@pytest.mark.parametrize("payload", [b"", b"mp3", b"RIFF", b"OggS" + bytes(100), None])
def test_malformed_audio_rejected(payload):
    with pytest.raises(VoiceError) as caught:
        validate_audio(payload)
    assert caught.value.code == ErrorCode.INVALID_AUDIO


@pytest.mark.parametrize(
    "options",
    [
        {"channels": 2},
        {"width": 1},
        {"width": 3},
        {"rate": 44100},
        {"frames": 0},
        {"frames": 1599},
        {"frames": 480001},
    ],
)
def test_unsupported_audio_limits(options):
    with pytest.raises(VoiceError) as caught:
        validate_audio(synthetic_wav(**options))
    assert caught.value.code == ErrorCode.UNSUPPORTED_AUDIO


def test_duration_upper_boundary():
    assert validate_audio(synthetic_wav(frames=480000)).duration_seconds == 30.0


def test_oversized_audio_fails_before_decode():
    with pytest.raises(VoiceError) as caught:
        validate_audio(bytes(MAX_AUDIO_BYTES + 1))
    assert caught.value.code == ErrorCode.AUDIO_TOO_LARGE


@pytest.mark.parametrize(
    "mutation",
    [
        "truncate",
        "append",
        "duplicate_data",
        "invalid_alignment",
        "fmt_size",
        "compressed",
        "missing_data",
        "odd_data",
    ],
)
def test_chunk_integrity(wav_bytes, mutation):
    payload = bytearray(wav_bytes)
    if mutation == "truncate":
        payload = payload[:-2]
    elif mutation == "append":
        payload += b"secret"
    elif mutation == "duplicate_data":
        payload += b"data" + struct.pack("<I", 2) + b"\0\0"
        struct.pack_into("<I", payload, 4, len(payload) - 8)
    elif mutation == "invalid_alignment":
        struct.pack_into("<H", payload, 32, 4)
    elif mutation == "fmt_size":
        struct.pack_into("<I", payload, 16, 10000)
    elif mutation == "compressed":
        struct.pack_into("<H", payload, 20, 3)
    elif mutation == "missing_data":
        payload[36:40] = b"JUNK"
    else:
        struct.pack_into("<I", payload, 40, 3199)
    with pytest.raises(VoiceError):
        validate_audio(bytes(payload))


def test_file_read_is_bounded_and_safe(wav_file, tmp_path):
    assert read_audio(wav_file).duration_seconds == 0.1
    with pytest.raises(VoiceError) as caught:
        read_audio(tmp_path / "private-path-secret.wav")
    assert str(caught.value) == "io_failed"


@pytest.mark.parametrize("language", list(Language))
def test_language_contract(language, wav_bytes):
    adapter = SyntheticAdapter()
    result = TranscriptionService(adapter).transcribe(wav_bytes, language.value)
    assert adapter.calls == [language]
    assert result.transcript.language == language
    assert result.transcript.text == "Test transcript."
    assert result.transcript.raw_text == adapter.text
    assert result.total_ms >= result.stt_ms >= 0


@pytest.mark.parametrize("language", ["auto", "de", "english", "EN", "", None, ["ur"]])
def test_unknown_language_fails_closed(language):
    with pytest.raises(VoiceError) as caught:
        parse_language(language)
    assert caught.value.code == ErrorCode.UNSUPPORTED_LANGUAGE


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("  cafe\u0301\ttext\n", "café text"),
        ("اردو\u200c زبان", "اردو\u200c زبان"),
        ("سنڌي", "سنڌي"),
        ("پښتو", "پښتو"),
        ("Don't Change—CASE!", "Don't Change—CASE!"),
        ("a\x00b\x7fc", "abc"),
        ("Ａ", "Ａ"),
        ("\r\n\t ", ""),
    ],
)
def test_conservative_unicode_normalization(raw, expected):
    assert normalize_transcript(raw) == expected


@pytest.mark.parametrize("raw", [None, "\ud800", "x" * 2049])
def test_invalid_transcripts(raw):
    with pytest.raises(VoiceError) as caught:
        normalize_transcript(raw)
    assert caught.value.code == ErrorCode.INVALID_TRANSCRIPT


def test_empty_transcript_is_not_a_placeholder(wav_bytes):
    with pytest.raises(VoiceError) as caught:
        TranscriptionService(SyntheticAdapter("\n\t ")).transcribe(wav_bytes, "en")
    assert caught.value.code == ErrorCode.EMPTY_TRANSCRIPT


def test_validation_precedes_model_invocation():
    adapter = SyntheticAdapter()
    with pytest.raises(VoiceError):
        TranscriptionService(adapter).transcribe(b"invalid", "en")
    assert not adapter.calls


def test_deterministic_serialization_and_observation_separation(wav_bytes):
    service = TranscriptionService(SyntheticAdapter())
    first, second = [service.transcribe(wav_bytes, "en") for _ in range(2)]
    assert first.transcript.checksum == second.transcript.checksum
    assert canonical_bytes(first.transcript.record()) == canonical_bytes(second.transcript.record())
    payload = canonical_bytes(first.transcript.record())
    assert payload.endswith(b"\n") and not payload.endswith(b"\n\n")
    assert b"timings" not in payload and b"total_ms" not in payload
    assert "timings_ms" in first.observation()
    assert "language_source" in first.transcript.semantic_record()


@pytest.mark.parametrize("change", ["text", "audio", "language", "model"])
def test_semantic_or_provenance_change_affects_checksum(change):
    base = build_transcript("0" * 64, Language.ENGLISH, MODEL_SPECS["whisper"], "Test")
    changed = build_transcript(
        "1" * 64 if change == "audio" else "0" * 64,
        Language.URDU if change == "language" else Language.ENGLISH,
        MODEL_SPECS["mms"] if change == "model" else MODEL_SPECS["whisper"],
        "Changed" if change == "text" else "Test",
    )
    assert base.checksum != changed.checksum


def test_factory_is_lazy_and_offline_by_default():
    for name in MODEL_SPECS:
        adapter = create_adapter(name)
        assert adapter.settings.local_files_only
        assert adapter._model is None
    with pytest.raises(VoiceError):
        create_adapter("other")
    with pytest.raises(VoiceError):
        RuntimeSettings("auto")


def test_no_cross_workstream_or_search_imports():
    package = Path(__file__).parents[2] / "src" / "sahulat_voice"
    forbidden = {
        "sahulat_text",
        "sahulat_database",
        "sahulat_visual",
        "sahulat_api",
        "integration",
        "psycopg",
        "fastapi",
        "open_clip",
        "sentence_transformers",
        "rank_bm25",
    }
    for source in package.glob("*.py"):
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                assert not any(name.name.split(".")[0] in forbidden for name in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden


def test_capabilities_no_model_load(capsys):
    assert main(["capabilities"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["search"] == "NOT_IMPLEMENTED"
    assert result["languages"] == ["en", "ur", "sd", "ps"]


def test_cli_transcription_writes_contract_and_metrics_only(
    monkeypatch, wav_file, tmp_path, capsys
):
    monkeypatch.setattr("sahulat_voice.cli.create_adapter", lambda *args: SyntheticAdapter())
    output = tmp_path / "transcript.json"
    original = wav_file.read_bytes()
    assert (
        main(
            [
                "transcribe",
                "--audio",
                str(wav_file),
                "--output",
                str(output),
                "--language",
                "en",
                "--model",
                "whisper",
            ]
        )
        == 0
    )
    assert wav_file.read_bytes() == original
    assert json.loads(output.read_bytes())["schema_version"] == "voice-transcript-v1"
    assert output.with_name(output.name + ".observation.json").is_file()
    assert "raw_text" not in capsys.readouterr().out


def test_cli_cannot_overwrite_audio(wav_file, capsys):
    before = wav_file.read_bytes()
    assert (
        main(
            [
                "transcribe",
                "--audio",
                str(wav_file),
                "--output",
                str(wav_file),
                "--language",
                "en",
                "--model",
                "mms",
            ]
        )
        == 1
    )
    assert wav_file.read_bytes() == before
    assert "invalid_config" in capsys.readouterr().err


def test_cli_safe_file_failure(tmp_path, capsys):
    assert (
        main(
            [
                "transcribe",
                "--audio",
                str(tmp_path / "secret.wav"),
                "--output",
                str(tmp_path / "out.json"),
                "--language",
                "en",
                "--model",
                "whisper",
            ]
        )
        == 1
    )
    error = capsys.readouterr().err
    assert "secret" not in error and "io_failed" in error


@pytest.mark.parametrize("identity", ["", "0" * 63, "X" * 64, None])
def test_malformed_audio_identity_rejected(identity):
    with pytest.raises(VoiceError) as caught:
        build_transcript(identity, Language.ENGLISH, MODEL_SPECS["whisper"], "Test")
    assert caught.value.code == ErrorCode.INVALID_TRANSCRIPT


def test_cli_cancellation_has_no_traceback(monkeypatch, wav_file, tmp_path, capsys):
    def interrupt(*args):
        raise KeyboardInterrupt

    monkeypatch.setattr("sahulat_voice.cli.create_adapter", interrupt)
    assert (
        main(
            [
                "transcribe",
                "--audio",
                str(wav_file),
                "--output",
                str(tmp_path / "out.json"),
                "--language",
                "en",
                "--model",
                "whisper",
            ]
        )
        == 130
    )
    assert json.loads(capsys.readouterr().err)["error"] == "cancelled"
    assert not (tmp_path / "out.json").exists()
