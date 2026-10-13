import os
from pathlib import Path

import pytest

from sahulat_voice.adapters import create_adapter
from sahulat_voice.evaluation import load_evaluation_input, resolve_audio_path
from sahulat_voice.service import TranscriptionService


@pytest.mark.model
@pytest.mark.parametrize("model", ["whisper", "mms"])
def test_cached_model_with_explicit_human_audio_input(model):
    if os.environ.get("RUN_VOICE_MODEL_TESTS") != "1":
        pytest.skip("Opt-in STT smoke requires cached weights and explicitly supplied human audio")
    manifest_value = os.environ.get("VOICE_SMOKE_MANIFEST")
    root_value = os.environ.get("VOICE_SMOKE_AUDIO_ROOT")
    if not manifest_value or not root_value:
        pytest.fail("VOICE_SMOKE_MANIFEST and VOICE_SMOKE_AUDIO_ROOT are required")
    root = Path(root_value)
    inputs = load_evaluation_input(Path(manifest_value), root)
    assert inputs.samples, "Genuine human evaluation input is required"
    service = TranscriptionService(create_adapter(model))
    for sample in inputs.samples:
        audio_path = resolve_audio_path(root, sample.audio_path)
        result = service.transcribe(audio_path.read_bytes(), sample.language.value)
        assert result.transcript.text
        assert result.transcript.audio_sha256 == sample.audio_sha256
