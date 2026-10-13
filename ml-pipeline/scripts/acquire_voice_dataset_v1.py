"""Operational range downloader; does not modify the frozen benchmark implementation."""

import argparse
import hashlib
import json
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.client import IncompleteRead
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sahulat_voice.benchmark.io import put_immutable
from sahulat_voice.benchmark.protocol import protocol_inputs, verify_protocol
from sahulat_voice.benchmark.source import SourceAsset, asset_from_record, validate_cached
from sahulat_voice.errors import ErrorCode, VoiceError

BLOCK_BYTES = 4 * 1024 * 1024
MAX_ATTEMPTS = 5


def acquire_block(asset: SourceAsset, revision: str, blocks: Path, index: int) -> Path:
    start = index * BLOCK_BYTES
    length = min(BLOCK_BYTES, asset.size - start)
    if length <= 0:
        raise VoiceError(ErrorCode.INVALID_CONFIG)
    path = blocks / f"{index:06d}.part"
    if not path.resolve().is_relative_to(blocks.resolve()):
        raise VoiceError(ErrorCode.INVALID_CONFIG)
    if path.exists():
        if path.stat().st_size != length:
            raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
        return path
    end = start + length - 1
    # A distinct public query key per range avoids reuse of an unrelated cached CDN range.
    url = (
        f"https://huggingface.co/datasets/google/fleurs/resolve/{revision}/{asset.path}"
        f"?download=true&voice_range={start}"
    )
    for attempt in range(MAX_ATTEMPTS):
        try:
            request = Request(
                url, headers={"Range": f"bytes={start}-{end}", "Accept-Encoding": "identity"}
            )
            with urlopen(request, timeout=30) as response:
                if (
                    response.status != 206
                    or response.headers.get("Content-Range") != f"bytes {start}-{end}/{asset.size}"
                    or response.headers.get("Content-Encoding", "identity") != "identity"
                ):
                    raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
                payload = response.read(length + 1)
                if len(payload) != length:
                    raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
            put_immutable(path, payload)
            return path
        except HTTPError as error:
            if error.code not in (408, 429, 500, 502, 503, 504):
                raise VoiceError(ErrorCode.IO_FAILED) from None
        except (TimeoutError, URLError, ConnectionError, IncompleteRead):
            pass
        if attempt + 1 < MAX_ATTEMPTS:
            time.sleep(min(2**attempt, 8))
    raise VoiceError(ErrorCode.IO_FAILED)


def install_archive(source_root: Path, asset: SourceAsset, blocks: Path) -> Path:
    destination = (source_root / asset.path).resolve()
    if not destination.is_relative_to(source_root.resolve()):
        raise VoiceError(ErrorCode.INVALID_CONFIG)
    if destination.exists():
        return validate_cached(source_root, asset)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=destination.parent, suffix=".assembled")
    digest, size = hashlib.sha256(), 0
    try:
        with os.fdopen(descriptor, "wb") as output:
            for index in range((asset.size + BLOCK_BYTES - 1) // BLOCK_BYTES):
                path = blocks / f"{index:06d}.part"
                if not path.resolve().is_relative_to(blocks.resolve()):
                    raise VoiceError(ErrorCode.INVALID_CONFIG)
                with path.open("rb") as stream:
                    payload = stream.read(BLOCK_BYTES + 1)
                if len(payload) != min(BLOCK_BYTES, asset.size - index * BLOCK_BYTES):
                    raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
                digest.update(payload)
                output.write(payload)
                size += len(payload)
        # Cached fragments are untrusted until the WHOLE pinned object hash passes.
        if size != asset.size or digest.hexdigest() != asset.sha256:
            raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
        try:
            os.link(temporary, destination)
        except FileExistsError:
            validate_cached(source_root, asset)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return validate_cached(source_root, asset)


def acquire_archive(root: Path, asset: SourceAsset, revision: str, workers: int) -> Path:
    blocks = root / ".cache/voice/acquisition_v1" / revision / asset.sha256
    source_root = root / ".cache/voice/fleurs" / revision
    if any(not path.resolve().is_relative_to(root.resolve()) for path in (blocks, source_root)):
        raise VoiceError(ErrorCode.INVALID_CONFIG)
    blocks.mkdir(parents=True, exist_ok=True)
    if (source_root / asset.path).exists():
        return validate_cached(source_root, asset)
    received, last = 0, time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = [
            pool.submit(acquire_block, asset, revision, blocks, index)
            for index in range((asset.size + BLOCK_BYTES - 1) // BLOCK_BYTES)
        ]
        for job in as_completed(jobs):
            received += job.result().stat().st_size
            if received == asset.size or time.monotonic() - last >= 5:
                print(
                    json.dumps(
                        {
                            "asset": asset.path,
                            "received_bytes": received,
                            "expected_bytes": asset.size,
                        }
                    ),
                    flush=True,
                )
                last = time.monotonic()
    return install_archive(source_root, asset, blocks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Acquire the four frozen official FLEURS archives")
    parser.add_argument("--allow-download", action="store_true", required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)
    try:
        if not 1 <= args.workers <= 8:
            raise VoiceError(ErrorCode.INVALID_CONFIG)
        root = Path.cwd()
        verify_protocol(root)
        _, source = protocol_inputs(root)
        for specification in source["languages"].values():
            asset = asset_from_record(specification["archive"])
            acquire_archive(root, asset, source["revision"], args.workers)
            print(json.dumps({"asset": asset.path, "source_checksum": "VERIFIED"}), flush=True)
        print(
            json.dumps({"status": "ALL_PINNED_TEST_ARCHIVES_VERIFIED", "model_results": "NOT_RUN"}),
            flush=True,
        )
        return 0
    except VoiceError as error:
        print(json.dumps({"status": "FAILED", "error": error.code.value}), flush=True)
    except KeyboardInterrupt:
        print(json.dumps({"status": "FAILED", "error": "cancelled"}), flush=True)
        return 130
    except Exception as error:
        # Type names are useful diagnostics; upstream exception strings may contain signed URLs.
        print(
            json.dumps(
                {"status": "FAILED", "error": "io_failed", "error_type": type(error).__name__}
            ),
            flush=True,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
