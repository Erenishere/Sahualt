import hashlib
import io
import struct
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from .errors import ErrorCode, VoiceError

SAMPLE_RATE = 16_000
MAX_AUDIO_BYTES = 2 * 1024 * 1024
MIN_AUDIO_FRAMES = 1_600
MAX_AUDIO_FRAMES = 30 * SAMPLE_RATE


@dataclass(frozen=True)
class ValidatedAudio:
    """Immutable validated payload; consumers receive a separate sample buffer."""

    pcm: bytes
    sha256: str

    @property
    def duration_seconds(self) -> float:
        return len(self.pcm) / (2 * SAMPLE_RATE)

    def samples(self) -> NDArray[np.float32]:
        return np.frombuffer(self.pcm, dtype="<i2").astype(np.float32) / 32768.0


def _validate_chunks(payload: bytes) -> None:
    if (
        len(payload) < 44
        or payload[:4] != b"RIFF"
        or payload[8:12] != b"WAVE"
        or struct.unpack_from("<I", payload, 4)[0] != len(payload) - 8
    ):
        raise VoiceError(ErrorCode.INVALID_AUDIO)
    position = 12
    counts = {b"fmt ": 0, b"data": 0}
    while position < len(payload):
        if position + 8 > len(payload):
            raise VoiceError(ErrorCode.INVALID_AUDIO)
        name, size = struct.unpack_from("<4sI", payload, position)
        position += 8
        if position + size + (size % 2) > len(payload):
            raise VoiceError(ErrorCode.INVALID_AUDIO)
        if name in counts:
            counts[name] += 1
        if name == b"fmt ":
            # Intentionally exclude extensible/float/compressed WAV and ambiguous formats.
            if size != 16 or struct.unpack_from("<H", payload, position)[0] != 1:
                raise VoiceError(ErrorCode.UNSUPPORTED_AUDIO)
            _, channels, rate, byte_rate, alignment, bits = struct.unpack_from(
                "<HHIIHH", payload, position
            )
            if (channels, rate, byte_rate, alignment, bits) != (1, SAMPLE_RATE, 32_000, 2, 16):
                raise VoiceError(ErrorCode.UNSUPPORTED_AUDIO)
        if name == b"data" and size % 2:
            raise VoiceError(ErrorCode.INVALID_AUDIO)
        position += size + size % 2
    if counts != {b"fmt ": 1, b"data": 1}:
        raise VoiceError(ErrorCode.INVALID_AUDIO)


def validate_audio(payload: bytes) -> ValidatedAudio:
    if not isinstance(payload, bytes):
        raise VoiceError(ErrorCode.INVALID_AUDIO)
    if len(payload) > MAX_AUDIO_BYTES:
        raise VoiceError(ErrorCode.AUDIO_TOO_LARGE)
    _validate_chunks(payload)
    try:
        with wave.open(io.BytesIO(payload), "rb") as source:
            frames = source.getnframes()
            if not MIN_AUDIO_FRAMES <= frames <= MAX_AUDIO_FRAMES:
                raise VoiceError(ErrorCode.UNSUPPORTED_AUDIO)
            pcm = source.readframes(frames)
            if len(pcm) != frames * 2:
                raise VoiceError(ErrorCode.INVALID_AUDIO)
    except (wave.Error, EOFError, OSError, struct.error):
        raise VoiceError(ErrorCode.INVALID_AUDIO) from None
    return ValidatedAudio(pcm, hashlib.sha256(payload).hexdigest())


def read_audio(path: Path) -> ValidatedAudio:
    try:
        with path.open("rb") as source:
            payload = source.read(MAX_AUDIO_BYTES + 1)
    except OSError:
        raise VoiceError(ErrorCode.IO_FAILED) from None
    return validate_audio(payload)
