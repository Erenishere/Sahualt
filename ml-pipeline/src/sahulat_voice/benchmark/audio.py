import hashlib
import io
import struct
import wave
from dataclasses import dataclass

import numpy as np

from ..audio import MAX_AUDIO_FRAMES, MIN_AUDIO_FRAMES, SAMPLE_RATE, validate_audio
from ..errors import ErrorCode, VoiceError

PREPARATION_VERSION = "fleurs-pcm16-v1"
MAX_SOURCE_WAV_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class PreparedAudio:
    wav: bytes
    source_sha256: str
    sha256: str
    frames: int
    source_format: str
    quantization_clipped_samples: int

    def evidence(self) -> dict[str, object]:
        return {
            "preparation_version": PREPARATION_VERSION,
            "source_sha256": self.source_sha256,
            "prepared_sha256": self.sha256,
            "frames": self.frames,
            "sample_rate": SAMPLE_RATE,
            "source_format": self.source_format,
            "quantization_clipped_samples": self.quantization_clipped_samples,
        }


def prepare_wav(payload: bytes, expected_frames: int) -> PreparedAudio:
    """Offline source adapter only. No runtime format broadening, resampling or denoising."""
    if (
        len(payload) < 44
        or len(payload) > MAX_SOURCE_WAV_BYTES
        or payload[:4] != b"RIFF"
        or payload[8:12] != b"WAVE"
        or struct.unpack_from("<I", payload, 4)[0] != len(payload) - 8
    ):
        raise VoiceError(ErrorCode.INVALID_AUDIO)
    position, format_bytes, data = 12, None, None
    while position < len(payload):
        if position + 8 > len(payload):
            raise VoiceError(ErrorCode.INVALID_AUDIO)
        name, length = struct.unpack_from("<4sI", payload, position)
        position += 8
        if position + length + length % 2 > len(payload):
            raise VoiceError(ErrorCode.INVALID_AUDIO)
        if name == b"fmt ":
            if format_bytes is not None:
                raise VoiceError(ErrorCode.INVALID_AUDIO)
            format_bytes = payload[position : position + length]
        elif name == b"data":
            if data is not None:
                raise VoiceError(ErrorCode.INVALID_AUDIO)
            data = payload[position : position + length]
        position += length + length % 2
    if format_bytes is None or len(format_bytes) not in (16, 18) or data is None:
        raise VoiceError(ErrorCode.UNSUPPORTED_AUDIO)
    if len(format_bytes) == 18 and format_bytes[16:] != b"\0\0":
        raise VoiceError(ErrorCode.UNSUPPORTED_AUDIO)
    encoding, channels, rate, byte_rate, alignment, bits = struct.unpack_from(
        "<HHIIHH", format_bytes
    )
    if (
        (encoding, bits) not in {(1, 16), (1, 32), (3, 32)}
        or channels != 1
        or rate != SAMPLE_RATE
        or alignment != bits // 8
        or byte_rate != SAMPLE_RATE * alignment
        or len(data) % alignment
    ):
        raise VoiceError(ErrorCode.UNSUPPORTED_AUDIO)
    frames = len(data) // alignment
    if frames != expected_frames or not MIN_AUDIO_FRAMES <= frames <= MAX_AUDIO_FRAMES:
        raise VoiceError(ErrorCode.INVALID_AUDIO)
    if (encoding, bits) == (1, 16):
        pcm, clipped, representation = data, 0, "pcm16"
    else:
        if encoding == 1:
            scaled = np.frombuffer(data, dtype="<i4").astype(np.float64) / 65536.0
            representation = "pcm32"
        else:
            samples = np.frombuffer(data, dtype="<f4").astype(np.float64)
            if not np.isfinite(samples).all():
                raise VoiceError(ErrorCode.INVALID_AUDIO)
            scaled = samples * 32768.0
            representation = "ieee-float32"
        rounded = np.rint(scaled)
        clipped = int(np.count_nonzero((rounded < -32768) | (rounded > 32767)))
        pcm = np.clip(rounded, -32768, 32767).astype("<i2").tobytes()
    stream = io.BytesIO()
    with wave.open(stream, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(pcm)
    canonical = stream.getvalue()
    audio = validate_audio(canonical)
    return PreparedAudio(
        canonical,
        hashlib.sha256(payload).hexdigest(),
        audio.sha256,
        frames,
        representation,
        clipped,
    )
