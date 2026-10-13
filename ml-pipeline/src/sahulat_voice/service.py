from dataclasses import dataclass
from time import perf_counter

from .adapters import STTAdapter
from .audio import validate_audio
from .contracts import BUILDER_VERSION, parse_language
from .transcript import Transcript, build_transcript


@dataclass(frozen=True)
class TranscriptionResult:
    transcript: Transcript
    audio_duration_seconds: float
    audio_validation_ms: float
    stt_ms: float
    model_load_ms: float
    total_ms: float

    def observation(self) -> dict[str, object]:
        return {
            "builder_version": BUILDER_VERSION,
            "transcript": self.transcript.record(),
            "audio_duration_seconds": self.audio_duration_seconds,
            "timings_ms": {
                "audio_validation": self.audio_validation_ms,
                "stt_including_load": self.stt_ms,
                "adapter_base_model_load": self.model_load_ms,
                "total": self.total_ms,
            },
        }


class TranscriptionService:
    def __init__(self, adapter: STTAdapter) -> None:
        self.adapter = adapter

    def transcribe(self, payload: bytes, language: str) -> TranscriptionResult:
        start = perf_counter()
        declared_language = parse_language(language)
        audio = validate_audio(payload)
        validation_ms = (perf_counter() - start) * 1000
        stt_start = perf_counter()
        raw = self.adapter.transcribe(audio, declared_language)
        stt_ms = (perf_counter() - stt_start) * 1000
        transcript = build_transcript(audio.sha256, declared_language, self.adapter.spec, raw)
        return TranscriptionResult(
            transcript,
            audio.duration_seconds,
            validation_ms,
            stt_ms,
            self.adapter.load_time_ms,
            (perf_counter() - start) * 1000,
        )
