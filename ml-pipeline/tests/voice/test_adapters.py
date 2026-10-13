import sys
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from sahulat_voice.adapters import create_adapter
from sahulat_voice.audio import validate_audio
from sahulat_voice.contracts import MMS_LANGUAGES, MODEL_SPECS, Language
from sahulat_voice.errors import ErrorCode, VoiceError
from sahulat_voice.service import TranscriptionService


@pytest.fixture
def backend(monkeypatch):
    torch = pytest.importorskip("torch", reason="Speech adapters require the existing ML extra")

    state = SimpleNamespace(loads=[], switches=[], generated=[], model=None, processor=None)

    class Batch(dict):
        def to(self, device):
            return self

    class Processor:
        @staticmethod
        def from_pretrained(repository, **options):
            state.loads.append(("processor", repository, options))
            state.processor = Processor()
            return state.processor

        def __init__(self):
            self.tokenizer = SimpleNamespace(
                vocab=dict.fromkeys(MMS_LANGUAGES.values()), set_target_lang=self.set_target_lang
            )
            self.target = "eng"

        def set_target_lang(self, target):
            self.target = target

        def __call__(self, samples, **options):
            assert options["sampling_rate"] == 16000
            assert len(samples) == 1600
            return Batch(input_values=torch.ones((1, 8)))

        def batch_decode(self, ids, **options):
            if state.model.target is not None:
                assert state.model.target == self.target
            return ["Synthetic " + self.target]

    class Model:
        @staticmethod
        def from_pretrained(repository, **options):
            state.loads.append(("model", repository, options))
            state.model = Model()
            return state.model

        def __init__(self):
            self.target = None
            self.config = SimpleNamespace(eos_token_id=2)

        def to(self, device):
            return self

        def eval(self):
            return self

        def requires_grad_(self, enabled):
            assert not enabled
            return self

        def generate(self, **options):
            state.generated.append(options)
            return torch.tensor([[1, 2]])

        def load_adapter(self, target, **options):
            state.switches.append((target, options))
            self.target = target

        def __call__(self, **options):
            return SimpleNamespace(logits=torch.tensor([[[0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]]))

    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(
            AutoProcessor=Processor, WhisperForConditionalGeneration=Model, Wav2Vec2ForCTC=Model
        ),
    )
    return state


@pytest.mark.parametrize("name", ["whisper", "mms"])
def test_model_pin_offline_safe_weights_and_once_loading(name, backend, wav_bytes):
    adapter = create_adapter(name)
    service = TranscriptionService(adapter)
    service.transcribe(wav_bytes, "en")
    service.transcribe(wav_bytes, "en")
    assert len(backend.loads) == 2
    for kind, repository, options in backend.loads:
        assert repository == MODEL_SPECS[name].repository
        assert options["revision"] == MODEL_SPECS[name].revision
        assert options["local_files_only"] is True
        assert options["token"] is False
        assert options["trust_remote_code"] is False
        assert "target_lang" not in options
        if kind == "model":
            assert options["use_safetensors"] is True
    assert adapter.load_time_ms >= 0


@pytest.mark.parametrize("language", list(Language))
def test_whisper_explicit_transcription_not_translation(language, backend, wav_bytes):
    TranscriptionService(create_adapter("whisper")).transcribe(wav_bytes, language.value)
    options = backend.generated[0]
    assert options["language"] == language.value
    assert options["task"] == "transcribe"
    assert not options["do_sample"]
    assert options["num_beams"] == 1
    assert options["max_new_tokens"] == 256
    assert not options["return_timestamps"]


@pytest.mark.parametrize("language", list(Language))
def test_mms_language_adapter_exact_script_and_revision(language, backend, wav_bytes):
    result = TranscriptionService(create_adapter("mms")).transcribe(wav_bytes, language.value)
    target, options = backend.switches[0]
    assert target == MMS_LANGUAGES[language]
    assert options["revision"] == MODEL_SPECS["mms"].revision
    assert options["use_safetensors"] and options["local_files_only"]
    assert result.transcript.text == "Synthetic " + target


def test_mms_language_switch_is_serialized(backend, wav_bytes):
    adapter = create_adapter("mms")
    audio = validate_audio(wav_bytes)
    languages = list(Language) * 4
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda lang: adapter.transcribe(audio, lang), languages))
    assert results == ["Synthetic " + MMS_LANGUAGES[language] for language in languages]
    assert len(backend.loads) == 2


@pytest.mark.parametrize("name", ["whisper", "mms"])
def test_upstream_load_errors_never_leak(name, backend, monkeypatch, wav_bytes):
    def fail(*args, **options):
        raise OSError("credential=secret C:/private/audio")

    monkeypatch.setattr(sys.modules["transformers"].AutoProcessor, "from_pretrained", fail)
    with pytest.raises(VoiceError) as caught:
        TranscriptionService(create_adapter(name)).transcribe(wav_bytes, "en")
    assert str(caught.value) == "model_unavailable"


@pytest.mark.parametrize("name", ["whisper", "mms"])
def test_upstream_inference_errors_never_leak(name, backend, wav_bytes):
    adapter = create_adapter(name)
    adapter._load()

    def fail(*args, **options):
        raise RuntimeError("secret in device and weights path")

    adapter._infer = fail
    with pytest.raises(VoiceError) as caught:
        adapter.transcribe(validate_audio(wav_bytes), Language.ENGLISH)
    assert str(caught.value) == "inference_failed"


def test_unknown_mms_language_not_silently_fallback(backend, wav_bytes):
    adapter = create_adapter("mms")
    adapter._load()
    backend.processor.tokenizer.vocab.pop("snd")
    with pytest.raises(VoiceError) as caught:
        adapter.transcribe(validate_audio(wav_bytes), Language.SINDHI)
    assert caught.value.code == ErrorCode.UNSUPPORTED_LANGUAGE
    assert not backend.switches


def test_missing_mms_adapter_safe_failure_and_retry(backend, wav_bytes):
    adapter = create_adapter("mms")
    adapter._load()
    real_load = backend.model.load_adapter

    def fail(*args, **options):
        raise OSError("missing cached adapter, secret path")

    backend.model.load_adapter = fail
    with pytest.raises(VoiceError) as caught:
        adapter.transcribe(validate_audio(wav_bytes), Language.URDU)
    assert caught.value.code == ErrorCode.MODEL_UNAVAILABLE
    assert adapter._active_language is None
    backend.model.load_adapter = real_load
    assert "urd-script_arabic" in adapter.transcribe(validate_audio(wav_bytes), Language.URDU)


def test_nonfinite_mms_logits_rejected(backend, wav_bytes):
    import torch

    adapter = create_adapter("mms")
    adapter._load()
    backend.model.__class__.__call__ = lambda *args, **options: SimpleNamespace(
        logits=torch.tensor([[[float("nan")]]])
    )
    with pytest.raises(VoiceError) as caught:
        adapter.transcribe(validate_audio(wav_bytes), Language.ENGLISH)
    assert caught.value.code == ErrorCode.INFERENCE_FAILED


def test_whisper_truncated_output_is_not_success(backend, wav_bytes):
    import torch

    adapter = create_adapter("whisper")
    adapter._load()
    backend.model.generate = lambda **options: torch.ones((1, 259), dtype=torch.long)
    with pytest.raises(VoiceError) as caught:
        adapter.transcribe(validate_audio(wav_bytes), Language.ENGLISH)
    assert caught.value.code == ErrorCode.INFERENCE_FAILED


def test_installed_whisper_preprocessing_without_extra_audio_packages():
    import numpy as np

    pytest.importorskip("torch")
    pytest.importorskip("transformers")
    from transformers.models.whisper.feature_extraction_whisper import WhisperFeatureExtractor

    batch = WhisperFeatureExtractor(feature_size=128)(
        np.zeros(1600, dtype=np.float32),
        sampling_rate=16000,
        return_tensors="pt",
        return_attention_mask=True,
    )
    assert tuple(batch["input_features"].shape) == (1, 128, 3000)
    assert tuple(batch["attention_mask"].shape) == (1, 3000)
