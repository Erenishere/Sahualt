import csv
import hashlib
import io
import re
from dataclasses import dataclass

from ..audio import MAX_AUDIO_FRAMES, MIN_AUDIO_FRAMES
from ..errors import ErrorCode, VoiceError
from ..transcript import normalize_transcript


@dataclass(frozen=True)
class FleursRow:
    sentence_id: int
    filename: str
    raw_transcription: str
    transcription: str
    frames: int
    source_row: int

    def selection_key(self, config: str) -> tuple[str, str]:
        key = f"EVAL-VOICE-V1|20260912|{config}|{self.filename}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest(), self.filename


def read_metadata(payload: bytes) -> tuple[list[FleursRow], list[dict[str, object]]]:
    try:
        decoded = payload.decode("utf-8")
        parsed = list(
            csv.reader(io.StringIO(decoded), delimiter="\t", quoting=csv.QUOTE_NONE, strict=True)
        )
    except (UnicodeError, csv.Error):
        raise VoiceError(ErrorCode.INVALID_MANIFEST) from None
    rows: list[FleursRow] = []
    excluded: list[dict[str, object]] = []
    filenames: set[str] = set()
    for position, record in enumerate(parsed, start=1):
        if len(record) != 7:
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        identifier, filename, raw, normalized, _, declared_frames, _ = record
        if (
            not re.fullmatch(r"[0-9]{1,20}", identifier)
            or not re.fullmatch(r"[0-9]{1,20}\.wav", filename)
            or not re.fullmatch(r"[0-9]{1,20}", declared_frames)
        ):
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        if filename in filenames:
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        filenames.add(filename)
        frames = int(declared_frames)
        reason = None
        try:
            if not normalize_transcript(raw) or not normalize_transcript(normalized):
                reason = "missing-reference"
        except VoiceError:
            reason = "invalid-reference"
        if not MIN_AUDIO_FRAMES <= frames <= MAX_AUDIO_FRAMES:
            reason = "outside-runtime-duration"
        if reason:
            excluded.append({"filename": filename, "source_row": position, "reason": reason})
        else:
            rows.append(FleursRow(int(identifier), filename, raw, normalized, frames, position))
    return rows, excluded


def select_rows(
    rows: list[FleursRow], config: str, count: int = 50
) -> tuple[list[FleursRow], list[dict[str, object]]]:
    if type(count) is not int or not 0 < count <= 50:
        raise VoiceError(ErrorCode.INVALID_CONFIG)
    references: dict[int, set[str]] = {}
    for row in rows:
        references.setdefault(row.sentence_id, set()).add(row.raw_transcription)
    conflicts = {identifier for identifier, values in references.items() if len(values) > 1}
    exclusions: list[dict[str, object]] = []
    selected: list[FleursRow] = []
    sentence_ids: set[int] = set()
    for row in sorted(rows, key=lambda item: item.selection_key(config)):
        if row.sentence_id in conflicts:
            reason = "conflicting-sentence-reference"
        elif row.sentence_id in sentence_ids:
            reason = "duplicate-sentence-reading"
        elif len(selected) == count:
            reason = "outside-frozen-subset"
        else:
            selected.append(row)
            sentence_ids.add(row.sentence_id)
            continue
        exclusions.append(
            {
                "filename": row.filename,
                "source_row": row.source_row,
                "sentence_id": row.sentence_id,
                "reason": reason,
            }
        )
    if len(selected) != count:
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    return selected, exclusions
