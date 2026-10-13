"""Acquire only verified specialist checkpoints; never runs an ASR model."""

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import urlopen

from acquire_voice_models_v1 import BLOCK_BYTES, SMALL_FILES, ModelAsset, block, install_model

from sahulat_voice.alternatives.metadata import (
    OUTPUT,
    candidates,
    preserve_official_metadata,
    snapshot,
    validate_official,
    verified_assets,
)
from sahulat_voice.benchmark.io import put_immutable, put_json
from sahulat_voice.errors import VoiceError


def acquire(root: Path, workers: int) -> None:
    for key, candidate in candidates(root).items():
        with urlopen(
            f"https://huggingface.co/api/models/{candidate['repository']}/revision/"
            f"{candidate['revision']}?blobs=true",
            timeout=30,
        ) as response:
            metadata = json.load(response)
        with urlopen(
            f"https://huggingface.co/{candidate['repository']}/resolve/"
            f"{candidate['revision']}/README.md",
            timeout=30,
        ) as response:
            readme = response.read(65537)
        validate_official(candidate, metadata, readme)
        preserve_official_metadata(
            root / OUTPUT / f"{key}-official-metadata.json",
            candidate,
            metadata,
            readme,
        )
        put_immutable(root / OUTPUT / f"{key}-README.md", readme)
        base = snapshot(root, candidate)
        base.mkdir(parents=True, exist_ok=True)
        wanted = SMALL_FILES | {"processor_config.json", "added_tokens.json", "model.safetensors"}
        evidence = []
        for item in sorted(metadata["siblings"], key=lambda i: i["rfilename"]):
            name = item["rfilename"]
            if name not in wanted:
                continue
            if "lfs" in item:
                asset = ModelAsset(name, item["lfs"]["sha256"], item["size"])
                folder = root / ".cache/voice/model_ranges" / asset.sha256
                folder.mkdir(parents=True, exist_ok=True)
                if not (base / name).exists():
                    with ThreadPoolExecutor(max_workers=workers) as pool:
                        futures = [
                            pool.submit(
                                block,
                                candidate["repository"],
                                candidate["revision"],
                                asset,
                                folder,
                                i,
                            )
                            for i in range((asset.size + BLOCK_BYTES - 1) // BLOCK_BYTES)
                        ]
                        count = 0
                        for future in as_completed(futures):
                            future.result()
                            count += 1
                            if count % 64 == 0:
                                print(
                                    json.dumps({"model": key, "downloaded_ranges": count}),
                                    flush=True,
                                )
                path = install_model(base, asset, folder)
                digest = asset.sha256
            else:
                with urlopen(
                    f"https://huggingface.co/{candidate['repository']}/resolve/"
                    f"{candidate['revision']}/{name}",
                    timeout=30,
                ) as response:
                    data = response.read(item["size"] + 1)
                blob = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
                if len(data) != item["size"] or blob != item["blobId"]:
                    from sahulat_voice.errors import ErrorCode

                    raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
                path = base / name
                put_immutable(path, data)
                digest = hashlib.sha256(data).hexdigest()
            evidence.append({"file": name, "size": path.stat().st_size, "sha256": digest})
        put_json(
            root / OUTPUT / f"{key}-acquisition.json",
            {
                "version": "voice-alt-acquisition-v1",
                "candidate": candidate,
                "files": evidence,
                "evaluation_independence": candidate["evaluation_independence"],
                "reason": candidate["reason"],
            },
        )
        verified_assets(root, key)
        print(json.dumps({"model": key, "status": "PINNED_ASSETS_VERIFIED"}), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-download", action="store_true", required=True)
    parser.add_argument("--workers", type=int, choices=range(1, 9), default=8)
    args = parser.parse_args()
    try:
        acquire(Path(__file__).resolve().parents[1], args.workers)
        return 0
    except VoiceError as error:
        print(json.dumps({"status": "FAILED", "error": error.code.value}), flush=True)
    except Exception as error:
        print(json.dumps({"status": "FAILED", "error_type": type(error).__name__}), flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
