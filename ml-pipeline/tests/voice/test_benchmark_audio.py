import hashlib
import io
import struct
import wave

import numpy as np
import pytest

from sahulat_voice.audio import validate_audio
from sahulat_voice.benchmark.audio import prepare_wav
from sahulat_voice.errors import VoiceError


def encoded_wav(values, encoding=3, bits=32, rate=16000, channels=1):
    """Synthetic conversion test signals, never benchmark speech."""
    dtype = {(3, 32): "<f4", (1, 32): "<i4", (1, 16): "<i2"}[(encoding, bits)]
    samples = np.resize(np.array(values, dtype=dtype), 1600)
    alignment = channels * bits // 8
    header = struct.pack("<HHIIHH", encoding, channels, rate, rate * alignment, alignment, bits)
    data = samples.tobytes()
    body = b"WAVEfmt " + struct.pack("<I", len(header)) + header
    body += b"data" + struct.pack("<I", len(data)) + data
    return b"RIFF" + struct.pack("<I", len(body)) + body


def pcm_values(wav):
    with wave.open(io.BytesIO(wav), "rb") as stream:
        return np.frombuffer(stream.readframes(stream.getnframes()), dtype="<i2")


def test_float32_ties_even_clipping_and_checksums():
    values = [0.5 / 32768, 1.5 / 32768, -0.5 / 32768, -1.5 / 32768, 1, -1, 2, -2]
    source = encoded_wav(values)
    result = prepare_wav(source, 1600)
    assert pcm_values(result.wav)[:8].tolist() == [0, 2, 0, -2, 32767, -32768, 32767, -32768]
    assert result.quantization_clipped_samples == 600
    assert result.source_format == "ieee-float32"
    assert result.source_sha256 == hashlib.sha256(source).hexdigest()
    assert result.sha256 == hashlib.sha256(result.wav).hexdigest()
    assert len(validate_audio(result.wav).pcm) // 2 == 1600
    assert prepare_wav(source, 1600) == result


def test_pcm32_quantization():
    result = prepare_wav(encoded_wav([32768, 98304, -98304, 2147483647], 1, 32), 1600)
    assert pcm_values(result.wav)[:4].tolist() == [0, 2, -2, 32767]
    assert result.source_format == "pcm32"


def test_pcm16_sample_bytes_preserved():
    source = encoded_wav([-32768, -1, 0, 32767], 1, 16)
    result = prepare_wav(source, 1600)
    assert result.wav == source
    assert result.quantization_clipped_samples == 0


def test_actual_fleurs_extended_float_format_supported():
    source = encoded_wav([0.25, -0.25])
    body = source[8:16] + struct.pack("<I", 18) + source[20:36] + b"\0\0" + source[36:]
    extended = b"RIFF" + struct.pack("<I", len(body)) + body
    assert prepare_wav(extended, 1600).wav == prepare_wav(source, 1600).wav


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_float_rejected(value):
    with pytest.raises(VoiceError):
        prepare_wav(encoded_wav([value]), 1600)


@pytest.mark.parametrize("frames", [1599, 1601, 0, 480001])
def test_metadata_frame_mismatch_rejected(frames):
    with pytest.raises(VoiceError):
        prepare_wav(encoded_wav([0]), frames)


@pytest.mark.parametrize("rate,channels", [(8000, 1), (44100, 1), (16000, 2)])
def test_no_silent_resampling_or_downmix(rate, channels):
    with pytest.raises(VoiceError):
        prepare_wav(encoded_wav([0], rate=rate, channels=channels), 1600)


@pytest.mark.parametrize("kind", ["truncated", "riff-size", "alignment", "duplicate-data"])
def test_malformed_wave_rejected(kind):
    payload = bytearray(encoded_wav([0]))
    if kind == "truncated":
        payload = payload[:-1]
    elif kind == "riff-size":
        payload[4:8] = struct.pack("<I", 1)
    elif kind == "alignment":
        payload[32:34] = struct.pack("<H", 2)
    else:
        payload.extend(b"data\0\0\0\0")
        payload[4:8] = struct.pack("<I", len(payload) - 8)
    with pytest.raises(VoiceError):
        prepare_wav(bytes(payload), 1600)


def test_runtime_still_rejects_native_float_and_pcm32():
    for encoding, bits in [(3, 32), (1, 32)]:
        source = encoded_wav([0], encoding, bits)
        with pytest.raises(VoiceError):
            validate_audio(source)
        validate_audio(prepare_wav(source, 1600).wav)
