from abc import ABC, abstractmethod
from threading import Lock
from time import perf_counter
from typing import Any

from .audio import SAMPLE_RATE, ValidatedAudio
from .contracts import MMS_LANGUAGES, MODEL_SPECS, Language, ModelSpec, RuntimeSettings
from .errors import ErrorCode, VoiceError


class STTAdapter(ABC):
    spec: ModelSpec
    load_time_ms: float = 0.0

    @abstractmethod
    def transcribe(self, audio: ValidatedAudio, language: Language) -> str:
        """Transcribe, never translate, caller-declared language audio."""


class HuggingFaceAdapter(STTAdapter):
    def __init__(self, settings: RuntimeSettings) -> None:
        self.settings = settings
        self._processor: Any = None
        self._model: Any = None
        self._lock = Lock()
        self.load_time_ms = 0.0

    def _load(self) -> None:
        if self._model is not None:
            return
        start = perf_counter()
        try:
            import torch
            from transformers import AutoProcessor, Wav2Vec2ForCTC, WhisperForConditionalGeneration

            if self.settings.device == "cuda" and not torch.cuda.is_available():
                raise VoiceError(ErrorCode.INVALID_CONFIG)
            options = {
                "revision": self.spec.revision,
                "local_files_only": self.settings.local_files_only,
                "trust_remote_code": False,
                "token": False,
            }
            processor = AutoProcessor.from_pretrained(self.spec.repository, **options)
            factory = (
                WhisperForConditionalGeneration
                if self.spec == MODEL_SPECS["whisper"]
                else Wav2Vec2ForCTC
            )
            model = factory.from_pretrained(
                self.spec.repository, **options, use_safetensors=True, dtype=torch.float32
            )
            model.to(self.settings.device).eval().requires_grad_(False)
            self._synchronize()
        except VoiceError:
            raise
        except Exception:
            raise VoiceError(ErrorCode.MODEL_UNAVAILABLE) from None
        # Publish both only after successful loading, so failure never leaves a half-ready adapter.
        self._processor, self._model = processor, model
        self.load_time_ms = (perf_counter() - start) * 1000

    def _synchronize(self) -> None:
        if self.settings.device == "cuda":
            import torch

            torch.cuda.synchronize()

    def transcribe(self, audio: ValidatedAudio, language: Language) -> str:
        if not isinstance(language, Language):
            raise VoiceError(ErrorCode.UNSUPPORTED_LANGUAGE)
        # MMS switches a shared tokenizer and adapter head; the entire operation must serialize.
        with self._lock:
            self._load()
            self._prepare_language(language)
            try:
                import torch

                self._synchronize()
                with torch.inference_mode():
                    raw = self._infer(audio, language)
                self._synchronize()
                if not isinstance(raw, str):
                    raise VoiceError(ErrorCode.INVALID_TRANSCRIPT)
                return raw
            except VoiceError:
                raise
            except Exception:
                raise VoiceError(ErrorCode.INFERENCE_FAILED) from None

    def _prepare_language(self, language: Language) -> None:
        return None

    @abstractmethod
    def _infer(self, audio: ValidatedAudio, language: Language) -> str:
        """Model-specific preprocessing and decoding live only inside the adapter."""


class WhisperAdapter(HuggingFaceAdapter):
    spec = MODEL_SPECS["whisper"]

    def _infer(self, audio: ValidatedAudio, language: Language) -> str:
        inputs = self._processor(
            audio.samples(),
            sampling_rate=SAMPLE_RATE,
            return_tensors="pt",
            return_attention_mask=True,
        ).to(self.settings.device)
        ids = self._model.generate(
            **inputs,
            language=language.value,
            task="transcribe",
            do_sample=False,
            num_beams=1,
            max_new_tokens=256,
            return_timestamps=False,
        )
        # Reaching the cap without EOS is a truncated transcript, not a valid silent success.
        if ids.shape[-1] >= 256 and ids[0, -1].item() != self._model.config.eos_token_id:
            raise VoiceError(ErrorCode.INFERENCE_FAILED)
        return self._processor.batch_decode(ids, skip_special_tokens=True)[0]


class MMSAdapter(HuggingFaceAdapter):
    spec = MODEL_SPECS["mms"]

    def __init__(self, settings: RuntimeSettings) -> None:
        super().__init__(settings)
        self._active_language: Language | None = None

    def _prepare_language(self, language: Language) -> None:
        if self._active_language == language:
            return
        self._active_language = None
        try:
            target = MMS_LANGUAGES[language]
            if target not in self._processor.tokenizer.vocab:
                raise VoiceError(ErrorCode.UNSUPPORTED_LANGUAGE)
            # Do not pass target_lang to from_pretrained: Transformers' automatic adapter
            # load drops our revision/offline arguments. Load explicitly with the same pin.
            self._model.load_adapter(
                target,
                revision=self.spec.revision,
                local_files_only=self.settings.local_files_only,
                use_safetensors=True,
                token=False,
            )
            self._processor.tokenizer.set_target_lang(target)
            self._model.eval().requires_grad_(False)
        except VoiceError:
            raise
        except Exception:
            raise VoiceError(ErrorCode.MODEL_UNAVAILABLE) from None
        self._active_language = language

    def _infer(self, audio: ValidatedAudio, language: Language) -> str:
        import torch

        inputs = self._processor(
            audio.samples(), sampling_rate=SAMPLE_RATE, return_tensors="pt"
        ).to(self.settings.device)
        logits = self._model(**inputs).logits
        if not torch.isfinite(logits).all().item():
            raise VoiceError(ErrorCode.INFERENCE_FAILED)
        ids = torch.argmax(logits, dim=-1)
        return self._processor.batch_decode(ids)[0]


def create_adapter(name: str, settings: RuntimeSettings | None = None) -> STTAdapter:
    configuration = settings or RuntimeSettings()
    if name == "whisper":
        return WhisperAdapter(configuration)
    if name == "mms":
        return MMSAdapter(configuration)
    raise VoiceError(ErrorCode.INVALID_CONFIG)
