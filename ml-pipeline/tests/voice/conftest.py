import io
import wave

import numpy as np
import pytest


def synthetic_wav(
    frames: int = 1600, channels: int = 1, width: int = 2, rate: int = 16000
) -> bytes:
    stream = io.BytesIO()
    with wave.open(stream, "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(width)
        output.setframerate(rate)
        output.writeframes(bytes(frames * channels * width))
    return stream.getvalue()


@pytest.fixture
def wav_bytes():
    # Silence is deliberately synthetic, not a human recording or an STT benchmark.
    return synthetic_wav()


@pytest.fixture
def wav_file(tmp_path, wav_bytes):
    path = tmp_path / "synthetic.wav"
    path.write_bytes(wav_bytes)
    return path


@pytest.fixture
def signal_bytes():
    stream = io.BytesIO()
    signal = (np.sin(np.arange(1600) * 0.1) * 32000).astype("<i2")
    with wave.open(stream, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(signal.tobytes())
    return stream.getvalue()
