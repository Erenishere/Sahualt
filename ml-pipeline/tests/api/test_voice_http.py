import hashlib
import io
import json
import wave
from collections.abc import Callable
from pathlib import Path
from threading import Event, Thread

import pytest
from fastapi.testclient import TestClient

from sahulat_api.voice import VoiceHttpSettings, create_voice_app
from sahulat_voice.adapters import STTAdapter
from sahulat_voice.audio import MAX_AUDIO_BYTES, ValidatedAudio
from sahulat_voice.contracts import MODEL_SPECS, Language
from sahulat_voice.service import TranscriptionService


def valid_wav() -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16_000)
        writer.writeframes(b"\0\0" * 1_600)
    return output.getvalue()


class FakeAdapter(STTAdapter):
    spec = MODEL_SPECS["whisper"]

    def __init__(self, wait: Callable[[], None] | None = None) -> None:
        self.wait = wait

    def transcribe(self, audio: ValidatedAudio, language: Language) -> str:
        if self.wait is not None:
            self.wait()
        return "  Hello   world  "


def app(adapter: STTAdapter | None = None):
    return create_voice_app(
        VoiceHttpSettings(),
        service_factory=lambda: TranscriptionService(adapter or FakeAdapter()),
    )


def test_versioned_contract_snapshot() -> None:
    expected = Path("configs/api/voice-http-v1.openapi.json").read_bytes()
    manifest = json.loads(Path("configs/api/voice-http-v1.manifest.json").read_text())
    current = (
        json.dumps(create_voice_app().openapi(), ensure_ascii=False, sort_keys=True, indent=2)
        + "\n"
    ).encode("utf-8")
    assert current == expected
    assert hashlib.sha256(expected).hexdigest() == manifest["openapi_sha256"]
    assert manifest["contract_version"] == "voice-http-v1"
    assert manifest["status"] == "FROZEN"


def test_transcription_response_is_bounded_and_provenance_aware() -> None:
    with TestClient(app()) as client:
        response = client.post(
            "/api/v1/transcriptions",
            content=valid_wav(),
            headers={"Content-Type": "audio/wav", "X-Voice-Language": "en"},
        )
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        body = response.json()
        assert set(body) == {
            "contract_version",
            "language",
            "text",
            "model",
            "revision",
            "audio_sha256",
            "transcript_checksum",
        }
        assert body["text"] == "Hello world"
        assert body["language"] == "en"
        assert body["model"] == "whisper-large-v3"
        assert len(body["audio_sha256"]) == 64
        assert body["transcript_checksum"].startswith("sha256:")
        assert client.get("/health/ready").status_code == 200


@pytest.mark.parametrize(
    ("headers", "payload", "expected"),
    [
        ({"Content-Type": "audio/wav", "X-Voice-Language": "sd"}, valid_wav(), 422),
        ({"Content-Type": "audio/wav", "X-Voice-Language": "xx"}, valid_wav(), 422),
        ({"Content-Type": "audio/wav", "X-Voice-Language": "en"}, b"bad", 400),
        ({"Content-Type": "audio/mpeg", "X-Voice-Language": "en"}, valid_wav(), 415),
        (
            {"Content-Type": "audio/wav", "X-Voice-Language": "en", "Content-Encoding": "gzip"},
            valid_wav(),
            415,
        ),
    ],
)
def test_request_rejection(headers: dict[str, str], payload: bytes, expected: int) -> None:
    with TestClient(app()) as client:
        response = client.post("/api/v1/transcriptions", content=payload, headers=headers)
        assert response.status_code == expected
        assert set(response.json()) == {"error"}
        assert response.headers["cache-control"] == "no-store"


def test_empty_model_cache_fails_readiness(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setattr("sahulat_api.voice.try_to_load_from_cache", lambda *a, **kw: None)
    with TestClient(create_voice_app()) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 503
        response = client.post(
            "/api/v1/transcriptions",
            content=valid_wav(),
            headers={"Content-Type": "audio/wav", "X-Voice-Language": "en"},
        )
        assert response.status_code == 503


def test_wrong_checkpoint_hash_fails_readiness(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    checkpoint = tmp_path / "model.safetensors"
    checkpoint.write_bytes(b"wrong model")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setattr(
        "sahulat_api.voice.try_to_load_from_cache", lambda *a, **kw: str(checkpoint)
    )
    with TestClient(create_voice_app()) as client:
        assert client.get("/health/ready").status_code == 503


def test_noncommercial_model_configuration_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_VOICE_MODEL", "mms")
    with TestClient(create_voice_app()) as client:
        assert client.get("/health/ready").status_code == 503


def test_unvalidated_languages_cannot_be_enabled() -> None:
    with pytest.raises(ValueError, match="Sindhi and Pashto"):
        VoiceHttpSettings(languages=frozenset(Language))


def test_english_and_urdu_are_explicit_paths() -> None:
    with TestClient(app()) as client:
        for code in ("en", "ur"):
            response = client.post(
                "/api/v1/transcriptions",
                content=valid_wav(),
                headers={"Content-Type": "audio/wav", "X-Voice-Language": code},
            )
            assert response.status_code == 200
            assert response.json()["language"] == code


def test_large_audio_is_rejected_before_inference() -> None:
    with TestClient(app()) as client:
        response = client.post(
            "/api/v1/transcriptions",
            content=b"x" * (MAX_AUDIO_BYTES + 1),
            headers={"Content-Type": "audio/wav", "X-Voice-Language": "en"},
        )
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "audio_too_large"


def test_duplicate_language_headers_are_rejected() -> None:
    with TestClient(app()) as client:
        response = client.post(
            "/api/v1/transcriptions",
            content=valid_wav(),
            headers=[
                ("Content-Type", "audio/wav"),
                ("X-Voice-Language", "en"),
                ("X-Voice-Language", "ur"),
            ],
        )
        assert response.status_code == 422


def test_unknown_route_uses_safe_error_shape() -> None:
    with TestClient(app()) as client:
        response = client.get("/missing")
        assert response.status_code == 404
        assert response.json() == {
            "error": {"code": "http_error", "message": "Request cannot be handled"}
        }


def test_busy_request_fails_without_queueing() -> None:
    started, release = Event(), Event()

    def wait() -> None:
        started.set()
        assert release.wait(5)

    with TestClient(app(FakeAdapter(wait))) as client:
        responses: list[int] = []

        def first() -> None:
            result = client.post(
                "/api/v1/transcriptions",
                content=valid_wav(),
                headers={"Content-Type": "audio/wav", "X-Voice-Language": "en"},
            )
            responses.append(result.status_code)

        worker = Thread(target=first)
        worker.start()
        try:
            assert started.wait(5)
            second = client.post(
                "/api/v1/transcriptions",
                content=valid_wav(),
                headers={"Content-Type": "audio/wav", "X-Voice-Language": "en"},
            )
            assert second.status_code == 503
            assert second.json()["error"]["code"] == "voice_busy"
        finally:
            release.set()
            worker.join(5)
        assert responses == [200]
