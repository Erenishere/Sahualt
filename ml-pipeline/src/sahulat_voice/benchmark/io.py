import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from ..errors import ErrorCode, VoiceError
from ..transcript import canonical_bytes


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        record: dict[str, object] = {}
        for key, value in pairs:
            if key in record:
                raise VoiceError(ErrorCode.INVALID_MANIFEST)
            record[key] = value
        return record

    with path.open("rb") as stream:
        data = stream.read(2 * 1024 * 1024 + 1)
    if len(data) > 2 * 1024 * 1024:
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=unique)
    except (ValueError, UnicodeError, RecursionError):
        raise VoiceError(ErrorCode.INVALID_MANIFEST) from None


def put_immutable(path: Path, payload: bytes) -> None:
    """Install without overwriting any different existing artifact, including concurrent writers."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
        return
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != payload:
                raise VoiceError(ErrorCode.CHECKSUM_MISMATCH) from None
    finally:
        Path(temporary).unlink(missing_ok=True)


def put_json(path: Path, record: object) -> None:
    put_immutable(path, canonical_bytes(record))


def read_canonical_json(path: Path) -> Any:
    record = read_json(path)
    if path.read_bytes() != canonical_bytes(record):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    return record


def record_checksum(record: object) -> str:
    return hashlib.sha256(canonical_bytes(record)).hexdigest()
