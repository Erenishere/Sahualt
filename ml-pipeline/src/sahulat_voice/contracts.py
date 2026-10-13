from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from .errors import ErrorCode, VoiceError

TRANSCRIPT_VERSION = "voice-transcript-v1"
NORMALIZATION_VERSION = "voice-nfc-whitespace-v1"
BUILDER_VERSION = "voice-stt-foundation-v1"


class Language(StrEnum):
    ENGLISH = "en"
    URDU = "ur"
    SINDHI = "sd"
    PASHTO = "ps"


def parse_language(value: str) -> Language:
    try:
        return Language(value)
    except (ValueError, TypeError):
        raise VoiceError(ErrorCode.UNSUPPORTED_LANGUAGE) from None


@dataclass(frozen=True)
class ModelSpec:
    name: str
    repository: str
    revision: str
    license: str


MODEL_SPECS = MappingProxyType(
    {
        "whisper": ModelSpec(
            "whisper-large-v3",
            "openai/whisper-large-v3",
            "06f233fe06e710322aca913c1bc4249a0d71fce1",
            "apache-2.0",
        ),
        "mms": ModelSpec(
            "mms-1b-all",
            "facebook/mms-1b-all",
            "3d33597edbdaaba14a8e858e2c8caa76e3cec0cd",
            "cc-by-nc-4.0",
        ),
    }
)
MMS_LANGUAGES = MappingProxyType(
    {
        Language.ENGLISH: "eng",
        Language.URDU: "urd-script_arabic",
        Language.SINDHI: "snd",
        Language.PASHTO: "pus",
    }
)


@dataclass(frozen=True)
class RuntimeSettings:
    device: str = "cpu"
    local_files_only: bool = True

    def __post_init__(self) -> None:
        if self.device not in {"cpu", "cuda"} or type(self.local_files_only) is not bool:
            raise VoiceError(ErrorCode.INVALID_CONFIG)
