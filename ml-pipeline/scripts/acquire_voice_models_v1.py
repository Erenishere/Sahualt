"""Acquire exact adapter assets separately from cold-load and scored inference timing."""

import argparse
import hashlib
import json
import os
import re
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from http.client import IncompleteRead
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sahulat_voice.benchmark.io import file_sha256, put_immutable, put_json
from sahulat_voice.contracts import MMS_LANGUAGES, MODEL_SPECS
from sahulat_voice.errors import ErrorCode, VoiceError

BLOCK_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True)
class ModelAsset:
    path: str
    sha256: str
    size: int

    def __post_init__(self) -> None:
        # Model checkpoints exceed the deliberately unchanged 1 GiB FLEURS object bound.
        if (
            not re.fullmatch(r"[a-zA-Z0-9_.-]+\.safetensors", self.path)
            or not re.fullmatch(r"[0-9a-f]{64}", self.sha256)
            or type(self.size) is not int
            or not 0 < self.size <= 8 * 1024**3
        ):
            raise VoiceError(ErrorCode.INVALID_MANIFEST)


def install_model(snapshot: Path, asset: ModelAsset, folder: Path) -> Path:
    destination = snapshot / asset.path
    if not destination.resolve().is_relative_to(snapshot.resolve()):
        raise VoiceError(ErrorCode.INVALID_CONFIG)
    if not destination.exists():
        descriptor, temporary = tempfile.mkstemp(dir=snapshot, suffix=".assembled")
        try:
            digest, total = hashlib.sha256(), 0
            with os.fdopen(descriptor, "wb") as stream:
                for index in range((asset.size + BLOCK_BYTES - 1) // BLOCK_BYTES):
                    path = folder / f"{index:06d}.part"
                    if not path.resolve().is_relative_to(folder.resolve()):
                        raise VoiceError(ErrorCode.INVALID_CONFIG)
                    with path.open("rb") as source:
                        data = source.read(BLOCK_BYTES + 1)
                    if len(data) != min(BLOCK_BYTES, asset.size - index * BLOCK_BYTES):
                        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
                    digest.update(data)
                    total += len(data)
                    stream.write(data)
            if total != asset.size or digest.hexdigest() != asset.sha256:
                raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
            try:
                os.link(temporary, destination)
            except FileExistsError:
                pass
        finally:
            Path(temporary).unlink(missing_ok=True)
    if destination.stat().st_size != asset.size or file_sha256(destination) != asset.sha256:
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    return destination


SMALL_FILES = {
    "config.json",
    "generation_config.json",
    "preprocessor_config.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "vocab.json",
    "merges.txt",
    "normalizer.json",
    "tokenizer.json",
}


def block(repository: str, revision: str, asset: ModelAsset, folder: Path, index: int) -> Path:
    start = index * BLOCK_BYTES
    size = min(BLOCK_BYTES, asset.size - start)
    path = folder / f"{index:06d}.part"
    if size <= 0 or start < 0 or not path.resolve().is_relative_to(folder.resolve()):
        raise VoiceError(ErrorCode.INVALID_CONFIG)
    if path.exists():
        if path.stat().st_size != size:
            raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
        return path
    request = Request(
        f"https://huggingface.co/{repository}/resolve/{revision}/{asset.path}"
        f"?download=true&voice_model_range={start}-{start + size - 1}",
        headers={"Range": f"bytes={start}-{start + size - 1}", "Accept-Encoding": "identity"},
    )
    for attempt in range(5):
        try:
            with urlopen(request, timeout=30) as response:
                if (
                    response.status != 206
                    or response.headers.get("Content-Range")
                    != f"bytes {start}-{start + size - 1}/{asset.size}"
                    or response.headers.get("Content-Encoding", "identity") != "identity"
                ):
                    raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
                data = response.read(size + 1)
            break
        except HTTPError as error:
            if error.code not in (408, 429, 500, 502, 503, 504):
                raise VoiceError(ErrorCode.IO_FAILED) from None
        except (TimeoutError, URLError, ConnectionError, IncompleteRead):
            pass
        print(
            json.dumps(
                {
                    "stage": "acquisition_only",
                    "asset": asset.path,
                    "range_start": start,
                    "transient_attempt": attempt + 1,
                }
            ),
            flush=True,
        )
        if attempt < 4:
            time.sleep(min(2**attempt, 8))
    else:
        raise VoiceError(ErrorCode.IO_FAILED)
    if len(data) != size:
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    put_immutable(path, data)
    return path


def acquire(root: Path, workers: int) -> dict:
    evidence = []
    for key, spec in MODEL_SPECS.items():
        with urlopen(
            f"https://huggingface.co/api/models/{spec.repository}/revision/"
            f"{spec.revision}?blobs=true",
            timeout=30,
        ) as response:
            metadata = json.load(response)
        if metadata["sha"] != spec.revision:
            raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
        wanted = SMALL_FILES | {"model.safetensors"}
        if key == "mms":
            wanted |= {f"adapter.{code}.safetensors" for code in MMS_LANGUAGES.values()}
        assets = [record for record in metadata["siblings"] if record["rfilename"] in wanted]
        found = {record["rfilename"] for record in assets}
        required = {
            "config.json",
            "preprocessor_config.json",
            "tokenizer_config.json",
            "vocab.json",
            "model.safetensors",
        }
        if key == "mms":
            required |= {f"adapter.{code}.safetensors" for code in MMS_LANGUAGES.values()}
        if not required <= found:
            raise VoiceError(ErrorCode.MODEL_UNAVAILABLE)
        snapshot = (
            root
            / ".cache/voice/huggingface/hub"
            / ("models--" + spec.repository.replace("/", "--"))
            / "snapshots"
            / spec.revision
        )
        if not snapshot.resolve().is_relative_to(root.resolve()):
            raise VoiceError(ErrorCode.INVALID_CONFIG)
        snapshot.mkdir(parents=True, exist_ok=True)
        checksums = []
        for record in sorted(assets, key=lambda record: record["rfilename"]):
            name = record["rfilename"]
            if "lfs" in record:
                asset = ModelAsset(name, record["lfs"]["sha256"], record["size"])
                folder = root / ".cache/voice/model_ranges" / asset.sha256
                if not folder.resolve().is_relative_to(root.resolve()):
                    raise VoiceError(ErrorCode.INVALID_CONFIG)
                folder.mkdir(parents=True, exist_ok=True)
                if not (snapshot / name).exists():
                    with ThreadPoolExecutor(max_workers=workers) as pool:
                        futures = [
                            pool.submit(block, spec.repository, spec.revision, asset, folder, i)
                            for i in range((asset.size + BLOCK_BYTES - 1) // BLOCK_BYTES)
                        ]
                        received = 0
                        for completed in as_completed(futures):
                            received += completed.result().stat().st_size
                            if (
                                received == asset.size
                                or received % (32 * BLOCK_BYTES) < BLOCK_BYTES
                            ):
                                print(
                                    json.dumps(
                                        {
                                            "model": key,
                                            "asset": name,
                                            "bytes": received,
                                            "total": asset.size,
                                        }
                                    ),
                                    flush=True,
                                )
                path = install_model(snapshot, asset, folder)
                digest = asset.sha256
            else:
                request = Request(
                    f"https://huggingface.co/{spec.repository}/resolve/"
                    f"{spec.revision}/{name}?download=true&voice_asset={record['blobId']}"
                )
                with urlopen(request, timeout=30) as response:
                    data = response.read(record["size"] + 1)
                if len(data) != record["size"]:
                    raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
                blob = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
                if blob != record["blobId"]:
                    raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
                path = snapshot / name
                put_immutable(path, data)
                digest = hashlib.sha256(data).hexdigest()
            checksums.append({"file": name, "size": path.stat().st_size, "sha256": digest})
        evidence.append(
            {
                "model": key,
                "repository": spec.repository,
                "revision": spec.revision,
                "files": checksums,
            }
        )
        print(json.dumps({"model": key, "status": "PINNED_ASSETS_VERIFIED"}), flush=True)
    result = {"version": "voice-model-acquisition-v1", "models": evidence}
    put_json(root / "artifacts/eval_voice_run_v1/model_acquisition.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-download", action="store_true", required=True)
    parser.add_argument("--workers", type=int, choices=range(1, 9), default=8)
    args = parser.parse_args()
    try:
        acquire(Path.cwd(), args.workers)
        return 0
    except VoiceError as error:
        print(json.dumps({"status": "FAILED", "error": error.code.value}), flush=True)
    except KeyboardInterrupt:
        print(json.dumps({"status": "CANCELLED"}), flush=True)
        return 130
    except Exception as error:
        # Never print signed redirect URLs or filesystem/credential details.
        print(json.dumps({"status": "FAILED", "error_type": type(error).__name__}), flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
