"""Internal, bounded HTTP serving for the pinned commercial-use Whisper adapter."""

import asyncio
import hashlib
import logging
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, Request
from huggingface_hub import try_to_load_from_cache
from pydantic import BaseModel, ConfigDict
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.requests import ClientDisconnect
from starlette.responses import JSONResponse

from sahulat_voice.adapters import WhisperAdapter
from sahulat_voice.audio import MAX_AUDIO_BYTES
from sahulat_voice.contracts import MODEL_SPECS, Language, RuntimeSettings, parse_language
from sahulat_voice.errors import ErrorCode, VoiceError
from sahulat_voice.service import TranscriptionResult, TranscriptionService

CONTRACT_VERSION = "voice-http-v1"
WHISPER_CHECKPOINT_SHA256 = "a8e94b85976e5864ba3e9525c7e6c83b2a1eca42d4b797a0c7c24d778e40fd95"
SERVING_LANGUAGES = frozenset({Language.ENGLISH, Language.URDU})
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VoiceHttpSettings:
    languages: frozenset[Language] = SERVING_LANGUAGES
    max_concurrent_requests: int = 1
    upload_timeout_seconds: float = 15.0

    def __post_init__(self) -> None:
        if not self.languages or any(not isinstance(item, Language) for item in self.languages):
            raise ValueError("AI_VOICE_LANGUAGES must contain supported language codes")
        if not self.languages <= SERVING_LANGUAGES:
            raise ValueError(
                "Sindhi and Pashto serving remain blocked pending independent evidence"
            )
        if type(self.max_concurrent_requests) is not int or self.max_concurrent_requests != 1:
            raise ValueError("AI_VOICE_MAX_CONCURRENT_REQUESTS must be 1 for the CPU adapter")
        if not 0 < self.upload_timeout_seconds <= 300:
            raise ValueError("AI_VOICE_UPLOAD_TIMEOUT_SECONDS must be in (0, 300]")

    @classmethod
    def from_env(cls) -> "VoiceHttpSettings":
        if os.getenv("AI_VOICE_MODEL", "whisper") != "whisper":
            raise ValueError("Only the pinned Whisper model is permitted for this service")
        codes = os.getenv("AI_VOICE_LANGUAGES", "en,ur").split(",")
        if len(codes) != len(set(codes)):
            raise ValueError("AI_VOICE_LANGUAGES contains duplicate codes")
        return cls(
            languages=frozenset(parse_language(code) for code in codes),
            max_concurrent_requests=int(os.getenv("AI_VOICE_MAX_CONCURRENT_REQUESTS", "1")),
            upload_timeout_seconds=float(os.getenv("AI_VOICE_UPLOAD_TIMEOUT_SECONDS", "15")),
        )


class VoiceHttpFailure(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        self.status, self.code, self.message = status, code, message


class VoiceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    contract_version: Literal["voice-http-v1"] = "voice-http-v1"
    language: str
    text: str
    model: str
    revision: str
    audio_sha256: str
    transcript_checksum: str


class ErrorDetails(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    code: str
    message: str


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    error: ErrorDetails


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status: {"model": ErrorResponse, "description": description}
    for status, description in [
        (400, "Malformed or unsupported WAV audio"),
        (408, "Audio upload timeout or disconnect"),
        (413, "Audio byte limit exceeded"),
        (415, "Unsupported request encoding or media type"),
        (422, "Unsupported language, empty transcript or query fields"),
        (500, "Transcription failed"),
        (503, "Voice model unavailable or busy"),
    ]
}


def load_voice_service() -> TranscriptionService:
    """Verify the cached checkpoint and load it before readiness becomes true."""
    if os.getenv("HF_HUB_OFFLINE") != "1":
        raise VoiceError(ErrorCode.INVALID_CONFIG)
    spec = MODEL_SPECS["whisper"]
    cached = try_to_load_from_cache(spec.repository, "model.safetensors", revision=spec.revision)
    if not isinstance(cached, str) or not Path(cached).is_file():
        raise VoiceError(ErrorCode.MODEL_UNAVAILABLE)
    try:
        with Path(cached).open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
    except OSError:
        raise VoiceError(ErrorCode.MODEL_UNAVAILABLE) from None
    if digest != WHISPER_CHECKPOINT_SHA256:
        raise VoiceError(ErrorCode.MODEL_UNAVAILABLE)
    adapter = WhisperAdapter(RuntimeSettings(device="cpu", local_files_only=True))
    # The frozen adapter is lazy; startup loads the exact same path without decoding audio.
    adapter._load()
    return TranscriptionService(adapter)


def voice_failure(error: VoiceError) -> VoiceHttpFailure:
    code = error.code
    if code == ErrorCode.AUDIO_TOO_LARGE:
        return VoiceHttpFailure(413, code.value, "Audio exceeds the byte limit")
    if code in {ErrorCode.INVALID_AUDIO, ErrorCode.UNSUPPORTED_AUDIO}:
        return VoiceHttpFailure(400, code.value, "Use mono PCM16 WAV at 16 kHz, 0.1 to 30 seconds")
    if code in {ErrorCode.UNSUPPORTED_LANGUAGE, ErrorCode.EMPTY_TRANSCRIPT}:
        return VoiceHttpFailure(422, code.value, "Audio or language cannot be transcribed")
    if code in {ErrorCode.MODEL_UNAVAILABLE, ErrorCode.INVALID_CONFIG}:
        return VoiceHttpFailure(503, "voice_unavailable", "Voice service is not ready")
    return VoiceHttpFailure(500, "voice_error", "Voice transcription failed")


def create_voice_app(
    settings: VoiceHttpSettings | None = None,
    *,
    service_factory: Callable[[], TranscriptionService] | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.service = None
        try:
            active = settings or VoiceHttpSettings.from_env()
            service = await run_in_threadpool(service_factory or load_voice_service)
            slots: asyncio.Queue[None] = asyncio.Queue(active.max_concurrent_requests)
            for _ in range(active.max_concurrent_requests):
                slots.put_nowait(None)
            app.state.settings, app.state.slots, app.state.service = active, slots, service
        except Exception as exc:
            logger.error("voice_startup_failed", extra={"error_type": type(exc).__name__})
        try:
            yield
        finally:
            app.state.service = None

    app = FastAPI(
        title="Sahulat AI Voice Runtime",
        version=CONTRACT_VERSION,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )
    app.state.service = None

    @app.exception_handler(VoiceHttpFailure)
    async def expected_error(request: Request, exc: VoiceHttpFailure) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": exc.code, "message": exc.message}},
            status_code=exc.status,
            headers={"Cache-Control": "no-store"},
        )

    @app.exception_handler(HTTPException)
    async def routing_error(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": "http_error", "message": "Request cannot be handled"}},
            status_code=exc.status_code,
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/health/ready", responses={503: ERROR_RESPONSES[503]})
    async def ready() -> dict[str, str]:
        if app.state.service is None:
            raise VoiceHttpFailure(503, "voice_unavailable", "Voice service is not ready")
        return {"status": "ready", "contract_version": CONTRACT_VERSION}

    @app.post(
        "/api/v1/transcriptions",
        response_model=VoiceResponse,
        responses=ERROR_RESPONSES,
        openapi_extra={
            "parameters": [
                {
                    "name": "X-Voice-Language",
                    "in": "header",
                    "required": True,
                    "schema": {"type": "string", "enum": ["en", "ur"]},
                }
            ],
            "requestBody": {
                "required": True,
                "content": {"audio/wav": {"schema": {"type": "string", "format": "binary"}}},
            },
        },
    )
    async def transcribe(request: Request) -> JSONResponse:
        service: TranscriptionService | None = app.state.service
        if service is None:
            raise VoiceHttpFailure(503, "voice_unavailable", "Voice service is not ready")
        active: VoiceHttpSettings = app.state.settings
        if len(request.headers.getlist("x-voice-language")) != 1:
            raise VoiceHttpFailure(422, "unsupported_language", "Declare one language")
        try:
            language = parse_language(request.headers.get("x-voice-language", ""))
        except VoiceError as exc:
            raise voice_failure(exc) from exc
        if language not in active.languages:
            raise VoiceHttpFailure(422, "unsupported_language", "Language is not enabled")
        slots: asyncio.Queue[None] = app.state.slots
        try:
            slots.get_nowait()
        except asyncio.QueueEmpty as exc:
            raise VoiceHttpFailure(503, "voice_busy", "Voice service is busy; retry later") from exc
        release_slot = True
        try:
            if request.url.query:
                raise VoiceHttpFailure(422, "invalid_fields", "Query parameters are not accepted")
            if request.headers.get("content-encoding", "identity") != "identity":
                raise VoiceHttpFailure(
                    415, "unsupported_encoding", "Compressed audio is not accepted"
                )
            if request.headers.get("content-type", "").lower() != "audio/wav":
                raise VoiceHttpFailure(415, "unsupported_media_type", "Use audio/wav")
            declared = request.headers.get("content-length")
            if declared is not None:
                if not declared.isascii() or not declared.isdecimal() or len(declared) > 10:
                    raise VoiceHttpFailure(400, "invalid_length", "Invalid Content-Length")
                if int(declared) > MAX_AUDIO_BYTES:
                    raise VoiceHttpFailure(413, "audio_too_large", "Audio exceeds the byte limit")
            body = bytearray()
            async with asyncio.timeout(active.upload_timeout_seconds):
                async for chunk in request.stream():
                    if len(body) + len(chunk) > MAX_AUDIO_BYTES:
                        raise VoiceHttpFailure(
                            413, "audio_too_large", "Audio exceeds the byte limit"
                        )
                    body.extend(chunk)
            if declared is not None and int(declared) != len(body):
                raise VoiceHttpFailure(
                    400, "invalid_length", "Content-Length does not match request bytes"
                )
            job = asyncio.create_task(
                run_in_threadpool(service.transcribe, bytes(body), language.value)
            )
            del body
            try:
                result: TranscriptionResult = await asyncio.shield(job)
            except asyncio.CancelledError:
                release_slot = False

                def release_after_work(done: asyncio.Task[TranscriptionResult]) -> None:
                    if not done.cancelled():
                        failure = done.exception()
                        if (
                            isinstance(failure, VoiceError)
                            and failure.code == ErrorCode.MODEL_UNAVAILABLE
                        ):
                            app.state.service = None
                    slots.put_nowait(None)

                job.add_done_callback(release_after_work)
                raise
            transcript = result.transcript
            payload = VoiceResponse(
                language=transcript.language.value,
                text=transcript.text,
                model=transcript.model.name,
                revision=transcript.model.revision,
                audio_sha256=transcript.audio_sha256,
                transcript_checksum=transcript.checksum,
            )
            return JSONResponse(payload.model_dump(), headers={"Cache-Control": "no-store"})
        except VoiceHttpFailure:
            raise
        except (TimeoutError, ClientDisconnect) as exc:
            raise VoiceHttpFailure(408, "upload_timeout", "Audio upload did not complete") from exc
        except VoiceError as exc:
            if exc.code == ErrorCode.MODEL_UNAVAILABLE:
                app.state.service = None
            raise voice_failure(exc) from exc
        except Exception as exc:
            logger.error("voice_request_failed", extra={"error_type": type(exc).__name__})
            raise VoiceHttpFailure(500, "voice_error", "Voice transcription failed") from exc
        finally:
            if release_slot:
                slots.put_nowait(None)

    return app
