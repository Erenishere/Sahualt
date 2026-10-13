import hashlib
import os
import re
import tempfile
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from ..errors import ErrorCode, VoiceError
from .io import file_sha256, read_json


@dataclass(frozen=True)
class SourceAsset:
    path: str
    sha256: str
    size: int

    def __post_init__(self) -> None:
        relative = PurePosixPath(self.path)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or "\\" in self.path
            or ":" in self.path
            or relative.as_posix() != self.path
            or not re.fullmatch(r"[0-9a-f]{64}", self.sha256)
            or type(self.size) is not int
            or not 0 < self.size <= 1024 * 1024 * 1024
        ):
            raise VoiceError(ErrorCode.INVALID_MANIFEST)


def asset_from_record(record: object) -> SourceAsset:
    if not isinstance(record, dict) or set(record) != {"path", "sha256", "size"}:
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    if not isinstance(record["path"], str) or not isinstance(record["sha256"], str):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    return SourceAsset(record["path"], record["sha256"], record["size"])


def validate_cached(root: Path, asset: SourceAsset) -> Path:
    path = (root / asset.path).resolve()
    if not path.is_relative_to(root.resolve()):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    if path.stat().st_size != asset.size or file_sha256(path) != asset.sha256:
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    return path


def acquire_asset(
    root: Path,
    asset: SourceAsset,
    revision: str,
    progress: Callable[[int, int], None] | None = None,
) -> Path:
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    destination = (root / asset.path).resolve()
    if not destination.is_relative_to(root.resolve()):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    if destination.exists():
        return validate_cached(root, asset)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=destination.parent, suffix=".download")
    try:
        request = urllib.request.Request(
            f"https://huggingface.co/datasets/google/fleurs/resolve/{revision}/{asset.path}",
            headers={"User-Agent": "Sahulat-VOICE-benchmark-preparation-v1"},
        )
        digest, received = hashlib.sha256(), 0
        with os.fdopen(descriptor, "wb") as output:
            with urllib.request.urlopen(request, timeout=30) as response:
                while chunk := response.read(1024 * 1024):
                    received += len(chunk)
                    if received > asset.size:
                        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
                    output.write(chunk)
                    digest.update(chunk)
                    if progress:
                        progress(received, asset.size)
        if received != asset.size or digest.hexdigest() != asset.sha256:
            raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
        try:
            os.link(temporary, destination)
        except FileExistsError:
            return validate_cached(root, asset)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return destination


def load_source_lock(path: Path) -> dict:
    document = read_json(path)
    if (
        not isinstance(document, dict)
        or set(document)
        != {"schema_version", "repository", "revision", "license", "card", "languages"}
        or document["schema_version"] != "fleurs-source-lock-v1"
        or document["repository"] != "google/fleurs"
        or document["license"] != "cc-by-4.0"
        or not isinstance(document["revision"], str)
        or not re.fullmatch(r"[0-9a-f]{40}", document["revision"])
        or not isinstance(document["languages"], dict)
        or set(document["languages"]) != {"en", "ur", "sd", "ps"}
    ):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    if asset_from_record(document["card"]).path != "README.md":
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    configs = {"en": "en_us", "ur": "ur_pk", "sd": "sd_in", "ps": "ps_af"}
    for language, config in configs.items():
        source = document["languages"][language]
        if (
            not isinstance(source, dict)
            or set(source) != {"config", "rows", "metadata", "archive"}
            or source["config"] != config
            or type(source["rows"]) is not int
            or not 0 < source["rows"] <= 10000
            or asset_from_record(source["metadata"]).path != f"data/{config}/test.tsv"
            or asset_from_record(source["archive"]).path != f"data/{config}/audio/test.tar.gz"
        ):
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
    return document
