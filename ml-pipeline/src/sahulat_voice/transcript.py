import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass

from .contracts import NORMALIZATION_VERSION, TRANSCRIPT_VERSION, Language, ModelSpec
from .errors import ErrorCode, VoiceError

MAX_TRANSCRIPT_CHARACTERS = 2048


def normalize_transcript(raw: str) -> str:
    if (
        not isinstance(raw, str)
        or len(raw) > MAX_TRANSCRIPT_CHARACTERS
        or any(unicodedata.category(char) == "Cs" for char in raw)
    ):
        raise VoiceError(ErrorCode.INVALID_TRANSCRIPT)
    normalized = unicodedata.normalize("NFC", raw)
    cleaned = "".join(
        char for char in normalized if unicodedata.category(char) != "Cc" or char.isspace()
    )
    return " ".join(cleaned.split())


def canonical_bytes(record: object) -> bytes:
    return (
        json.dumps(
            record, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        + "\n"
    ).encode("utf-8")


@dataclass(frozen=True)
class Transcript:
    audio_sha256: str
    language: Language
    model: ModelSpec
    raw_text: str
    text: str

    def semantic_record(self) -> dict[str, object]:
        return {
            "schema_version": TRANSCRIPT_VERSION,
            "normalization_version": NORMALIZATION_VERSION,
            "audio_sha256": self.audio_sha256,
            "language": self.language.value,
            "language_source": "caller_declared",
            "model": {
                "name": self.model.name,
                "repository": self.model.repository,
                "revision": self.model.revision,
            },
            "raw_text": self.raw_text,
            "text": self.text,
        }

    @property
    def checksum(self) -> str:
        return "sha256:" + hashlib.sha256(canonical_bytes(self.semantic_record())).hexdigest()

    def record(self) -> dict[str, object]:
        return {**self.semantic_record(), "transcript_checksum": self.checksum}


def build_transcript(
    audio_sha256: str, language: Language, model: ModelSpec, raw: str
) -> Transcript:
    if (
        not isinstance(audio_sha256, str)
        or not re.fullmatch(r"[0-9a-f]{64}", audio_sha256)
        or not isinstance(language, Language)
        or not isinstance(model, ModelSpec)
    ):
        raise VoiceError(ErrorCode.INVALID_TRANSCRIPT)
    normalized = normalize_transcript(raw)
    if not normalized:
        raise VoiceError(ErrorCode.EMPTY_TRANSCRIPT)
    return Transcript(audio_sha256, language, model, raw, normalized)
