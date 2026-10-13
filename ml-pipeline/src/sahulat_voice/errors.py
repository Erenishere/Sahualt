from enum import StrEnum


class ErrorCode(StrEnum):
    INVALID_AUDIO = "invalid_audio"
    AUDIO_TOO_LARGE = "audio_too_large"
    UNSUPPORTED_AUDIO = "unsupported_audio"
    UNSUPPORTED_LANGUAGE = "unsupported_language"
    INVALID_CONFIG = "invalid_config"
    MODEL_UNAVAILABLE = "model_unavailable"
    INFERENCE_FAILED = "inference_failed"
    INVALID_TRANSCRIPT = "invalid_transcript"
    EMPTY_TRANSCRIPT = "empty_transcript"
    INVALID_MANIFEST = "invalid_manifest"
    CHECKSUM_MISMATCH = "checksum_mismatch"
    IO_FAILED = "io_failed"
    CANCELLED = "cancelled"


class VoiceError(Exception):
    """Public failures contain only fixed messages, never upstream exceptions or paths."""

    def __init__(self, code: ErrorCode) -> None:
        self.code = code
        super().__init__(code.value)
