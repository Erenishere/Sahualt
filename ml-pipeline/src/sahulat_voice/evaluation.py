import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .audio import ValidatedAudio, read_audio
from .contracts import Language, parse_language
from .errors import ErrorCode, VoiceError
from .transcript import canonical_bytes, normalize_transcript

EVALUATION_SCHEMA = "voice-evaluation-input-v1"
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_EVALUATION_SAMPLES = 200


@dataclass(frozen=True)
class EvaluationSample:
    sample_id: str
    language: Language
    audio_path: str
    audio_sha256: str
    reference_text: str
    reference_author: str
    source: str


@dataclass(frozen=True)
class EvaluationInput:
    samples: tuple[EvaluationSample, ...]
    manifest_sha256: str

    def summary(self) -> dict[str, object]:
        return {
            "schema_version": EVALUATION_SCHEMA,
            "manifest_sha256": self.manifest_sha256,
            "sample_count": len(self.samples),
            "language_counts": {
                language.value: sum(sample.language == language for sample in self.samples)
                for language in Language
            },
            "human_evaluation_data": "SUPPLIED_NOT_YET_EVALUATED" if self.samples else "PENDING",
            "evaluation_results": "NOT_RUN",
        }


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        result[key] = value
    return result


def _bounded_string(value: object, maximum: int = 128) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > maximum
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise VoiceError(ErrorCode.INVALID_MANIFEST) from None
    return value


def resolve_audio_path(root: Path, reference: str) -> Path:
    relative = PurePosixPath(reference)
    if (
        not reference
        or relative.is_absolute()
        or ".." in relative.parts
        or "\\" in reference
        or ":" in reference
        or relative.as_posix() != reference
        or relative.suffix.lower() != ".wav"
    ):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    try:
        resolved = (root / reference).resolve()
        if not resolved.is_relative_to(root.resolve()):
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
    except (OSError, ValueError, RuntimeError):
        raise VoiceError(ErrorCode.INVALID_MANIFEST) from None
    return resolved


def read_evaluation_audio(root: Path, sample: EvaluationSample) -> ValidatedAudio:
    audio = read_audio(resolve_audio_path(root, sample.audio_path))
    if audio.sha256 != sample.audio_sha256:
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    return audio


def load_evaluation_input(manifest: Path, audio_root: Path) -> EvaluationInput:
    try:
        with manifest.open("rb") as stream:
            payload = stream.read(MAX_MANIFEST_BYTES + 1)
        if len(payload) > MAX_MANIFEST_BYTES:
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        document = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_object)
    except (OSError, ValueError, UnicodeError, RecursionError):
        raise VoiceError(ErrorCode.INVALID_MANIFEST) from None
    if (
        not isinstance(document, dict)
        or set(document) != {"schema_version", "samples"}
        or document["schema_version"] != EVALUATION_SCHEMA
        or not isinstance(document["samples"], list)
        or len(document["samples"]) > MAX_EVALUATION_SAMPLES
    ):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    expected = {
        "sample_id",
        "language",
        "audio_path",
        "audio_sha256",
        "reference_text",
        "reference_author",
        "reference_source",
        "source",
        "use_permission_confirmed",
    }
    samples: list[EvaluationSample] = []
    identifiers: set[str] = set()
    audio_checksums: set[str] = set()
    for record in document["samples"]:
        if not isinstance(record, dict) or set(record) != expected:
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        identifier = _bounded_string(record["sample_id"])
        checksum = _bounded_string(record["audio_sha256"])
        if (
            not re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", identifier)
            or not re.fullmatch(r"[0-9a-f]{64}", checksum)
            or identifier in identifiers
            or checksum in audio_checksums
            or record["reference_source"] != "human"
            or record["source"] not in ("human_recording", "licensed_dataset")
            or record["use_permission_confirmed"] is not True
        ):
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        reference = record["reference_text"]
        if not isinstance(reference, str) or not normalize_transcript(reference):
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        sample = EvaluationSample(
            identifier,
            parse_language(record["language"]),
            _bounded_string(record["audio_path"], 512),
            checksum,
            reference,
            _bounded_string(record["reference_author"]),
            record["source"],
        )
        read_evaluation_audio(audio_root, sample)
        samples.append(sample)
        identifiers.add(identifier)
        audio_checksums.add(checksum)
    # Preserve exact original reference strings; list insertion order is not manifest identity.
    ordered = {**document, "samples": sorted(document["samples"], key=lambda row: row["sample_id"])}
    return EvaluationInput(
        tuple(sorted(samples, key=lambda sample: sample.sample_id)),
        hashlib.sha256(canonical_bytes(ordered)).hexdigest(),
    )


def _distance(reference: list[str], hypothesis: list[str]) -> int:
    previous = list(range(len(hypothesis) + 1))
    for position, expected in enumerate(reference, start=1):
        current = [position]
        for index, actual in enumerate(hypothesis, start=1):
            current.append(
                min(
                    current[-1] + 1, previous[index] + 1, previous[index - 1] + (expected != actual)
                )
            )
        previous = current
    return previous[-1]


def transcript_error_counts(reference: str, hypothesis: str) -> dict[str, int | float]:
    """Scaffold only: reference labels must come from humans; no benchmark claim is implied."""
    expected = normalize_transcript(reference)
    actual = normalize_transcript(hypothesis)
    if not expected:
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    words = expected.split()
    word_errors = _distance(words, actual.split())
    character_errors = _distance(list(expected), list(actual))
    return {
        "reference_words": len(words),
        "reference_characters": len(expected),
        "word_errors": word_errors,
        "character_errors": character_errors,
        "wer": word_errors / len(words),
        "cer": character_errors / len(expected),
    }
