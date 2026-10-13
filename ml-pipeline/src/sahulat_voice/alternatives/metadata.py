import os
import re
from pathlib import Path
from typing import Any

from ..benchmark.io import file_sha256, put_json, read_canonical_json, read_json
from ..contracts import Language, ModelSpec
from ..errors import ErrorCode, VoiceError

CONFIG = "configs/voice_alt_v1_models.json"
OUTPUT = os.environ.get("SAHULAT_VOICE_ALT_OUTPUT", "artifacts/eval_voice_alt_v1")
ASSET_OUTPUT = os.environ.get("SAHULAT_VOICE_ALT_ASSET_OUTPUT", OUTPUT)


def candidates(root: Path) -> dict[str, Any]:
    config = read_json(root / CONFIG)
    if config.get("version") != "voice-alt-models-v1" or set(config.get("models", {})) != {
        "pashto-ghag",
        "buzzasr-sindhi",
    }:
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    for key, record in config["models"].items():
        if (
            not re.fullmatch(r"[0-9a-f]{40}", record["revision"])
            or not re.fullmatch(r"[0-9a-f]{64}", record["weights_sha256"])
            or record["license"] != ("apache-2.0" if key == "pashto-ghag" else "mit")
            or record["language"] != ("ps" if key == "pashto-ghag" else "sd")
            or record["evaluation_independence"] is not False
            or record["fleurs_training_declared"] is not (key == "buzzasr-sindhi")
            or (key == "buzzasr-sindhi" and record["reason"] != "model training includes FLEURS")
        ):
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
    return config["models"]


def spec(record: dict[str, Any]) -> ModelSpec:
    return ModelSpec(*(record[key] for key in ("name", "repository", "revision", "license")))


def snapshot(root: Path, record: dict[str, Any]) -> Path:
    return (
        root
        / ".cache/voice/huggingface/hub"
        / ("models--" + record["repository"].replace("/", "--"))
        / "snapshots"
        / record["revision"]
    )


def validate_official(record: dict[str, Any], metadata: dict[str, Any], readme: bytes) -> None:
    import hashlib

    card = metadata.get("cardData", {})
    languages = card.get("language")
    if isinstance(languages, str):
        languages = [languages]
    weights = [s for s in metadata.get("siblings", []) if s["rfilename"] == "model.safetensors"]
    blob = hashlib.sha1(f"blob {len(readme)}\0".encode() + readme).hexdigest()
    if (
        metadata.get("sha") != record["revision"]
        or metadata.get("id") != record["repository"]
        or card.get("license") != record["license"]
        or card.get("base_model") != record["base_model"]
        or languages != [record["language"]]
        or card.get("datasets") != record["declared_datasets"]
        or blob != record["readme_blob_id"]
        or len(weights) != 1
        or weights[0].get("lfs", {}).get("sha256") != record["weights_sha256"]
        or weights[0].get("size") != record["weights_bytes"]
    ):
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    text = readme.decode("utf-8").casefold()
    if record["fleurs_training_declared"]:
        if not all(term in text for term in ("training data", "fleurs", "goldfish", "25.0")):
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
    elif "fleurs" in text or "common voice" not in text:
        raise VoiceError(ErrorCode.INVALID_MANIFEST)


def preserve_official_metadata(
    path: Path,
    record: dict[str, Any],
    metadata: dict[str, Any],
    readme: bytes,
) -> dict[str, Any]:
    """Retain the first verified response while tolerating unrelated API counters."""
    validate_official(record, metadata, readme)
    if path.exists():
        preserved = read_canonical_json(path)
        validate_official(record, preserved, readme)
        return preserved
    put_json(path, metadata)
    return metadata


def verified_assets(root: Path, key: str) -> dict[str, Any]:
    import hashlib

    record = candidates(root)[key]
    evidence = read_canonical_json(root / ASSET_OUTPUT / f"{key}-acquisition.json")
    official = read_canonical_json(root / ASSET_OUTPUT / f"{key}-official-metadata.json")
    validate_official(record, official, (root / ASSET_OUTPUT / f"{key}-README.md").read_bytes())
    if (
        evidence["candidate"] != record
        or evidence.get("version") != "voice-alt-acquisition-v1"
        or evidence.get("evaluation_independence") is not False
        or evidence.get("reason") != record["reason"]
    ):
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    base = snapshot(root, record)
    names = [item["file"] for item in evidence["files"]]
    required = {
        "model.safetensors",
        "config.json",
        "tokenizer_config.json",
        "generation_config.json",
    }
    required |= (
        {"processor_config.json", "tokenizer.json"}
        if key == "pashto-ghag"
        else {"preprocessor_config.json", "vocab.json", "merges.txt", "added_tokens.json"}
    )
    if len(names) != len(set(names)) or not required <= set(names):
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    for item in evidence["files"]:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", item["file"]):
            raise VoiceError(ErrorCode.INVALID_MANIFEST)
        path = base / item["file"]
        if not path.resolve().is_relative_to(base.resolve()):
            raise VoiceError(ErrorCode.INVALID_CONFIG)
        if path.stat().st_size != item["size"] or file_sha256(path) != item["sha256"]:
            raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
        declarations = [s for s in official["siblings"] if s["rfilename"] == item["file"]]
        if len(declarations) != 1 or declarations[0]["size"] != item["size"]:
            raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
        declaration = declarations[0]
        if "lfs" not in declaration:
            if item["size"] > 8 * 1024 * 1024:
                raise VoiceError(ErrorCode.INVALID_MANIFEST)
            data = path.read_bytes()
            if (
                hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
                != declaration["blobId"]
            ):
                raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
        elif item["sha256"] != declaration["lfs"]["sha256"]:
            raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
        if item["file"] == "model.safetensors" and (
            item["sha256"] != record["weights_sha256"] or item["size"] != record["weights_bytes"]
        ):
            raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)
    return evidence


def language(record: dict[str, Any]) -> Language:
    return Language(record["language"])
