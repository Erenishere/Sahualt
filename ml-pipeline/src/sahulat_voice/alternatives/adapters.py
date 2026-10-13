from pathlib import Path
from time import perf_counter
from typing import Any

from ..adapters import WhisperAdapter
from ..audio import ValidatedAudio
from ..benchmark.io import read_json
from ..contracts import Language, RuntimeSettings
from ..errors import ErrorCode, VoiceError
from .metadata import candidates, language, snapshot, spec


class SpecialistWhisperAdapter(WhisperAdapter):
    """Reuse frozen Whisper decoding; select Whisper explicitly, not the legacy MMS branch."""

    def __init__(self, root: Path, key: str) -> None:
        super().__init__(RuntimeSettings("cpu", local_files_only=True))
        self.root, self.key = root, key
        records = candidates(root)
        if key not in records:
            raise VoiceError(ErrorCode.INVALID_CONFIG)
        self.candidate = records[key]
        self.spec = spec(self.candidate)
        self.declared_language = language(self.candidate)

    def _load(self) -> None:
        if self._model is not None:
            return
        start = perf_counter()
        try:
            import torch
            from transformers import (
                AutoProcessor,
                AutoTokenizer,
                WhisperFeatureExtractor,
                WhisperForConditionalGeneration,
                WhisperProcessor,
            )

            options: dict[str, Any] = {
                "revision": self.spec.revision,
                "local_files_only": True,
                "trust_remote_code": False,
                "token": False,
            }
            if self.key == "pashto-ghag":
                # Transformers 5 stores the same extractor inside processor_config.json.
                # Read it without rewriting cached assets or upgrading the frozen runtime.
                config = read_json(snapshot(self.root, self.candidate) / "processor_config.json")
                feature = config.get("feature_extractor", {})
                if (
                    config.get("processor_class") != "WhisperProcessor"
                    or feature.get("feature_extractor_type") != "WhisperFeatureExtractor"
                    or feature.get("sampling_rate") != 16000
                    or feature.get("feature_size") != 80
                    or feature.get("dither", 0) != 0
                ):
                    raise VoiceError(ErrorCode.INVALID_CONFIG)
                tokenizer_options = dict(options)
                tokenizer_config_path = (
                    snapshot(self.root, self.candidate) / "tokenizer_config.json"
                )
                if tokenizer_config_path.exists():
                    tokenizer_config = read_json(tokenizer_config_path)
                    extra_special_tokens = tokenizer_config.get("extra_special_tokens")
                    # Transformers 4.57 expects the published Transformers 5 list as a mapping.
                    if isinstance(extra_special_tokens, list):
                        tokenizer_options["extra_special_tokens"] = {
                            token: token for token in extra_special_tokens
                        }
                processor = WhisperProcessor(
                    WhisperFeatureExtractor(**feature),
                    AutoTokenizer.from_pretrained(self.spec.repository, **tokenizer_options),
                )
            else:
                processor = AutoProcessor.from_pretrained(self.spec.repository, **options)
            model = WhisperForConditionalGeneration.from_pretrained(
                self.spec.repository, **options, use_safetensors=True, dtype=torch.float32
            )
            if self.key == "buzzasr-sindhi":
                # The checkpoint's generation config is present on disk but is
                # not fully propagated by Transformers' model-config merge.
                generation_path = (
                    snapshot(self.root, self.candidate) / "generation_config.json"
                )
                if generation_path.exists():
                    generation = read_json(generation_path)
                    for field in ("lang_to_id", "task_to_id"):
                        if field in generation:
                            setattr(model.generation_config, field, generation[field])
            model.to("cpu").eval().requires_grad_(False)
        except VoiceError:
            raise
        except Exception:
            raise VoiceError(ErrorCode.MODEL_UNAVAILABLE) from None
        self._processor, self._model = processor, model
        self.load_time_ms = (perf_counter() - start) * 1000

    def transcribe(self, audio: ValidatedAudio, language: Language) -> str:
        if language != self.declared_language:
            raise VoiceError(ErrorCode.UNSUPPORTED_LANGUAGE)
        return super().transcribe(audio, language)
