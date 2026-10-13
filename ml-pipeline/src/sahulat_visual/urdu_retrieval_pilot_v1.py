"""Isolated Urdu FashionCLIP text-to-image retrieval pilot.

This module deliberately does not participate in Visual Retrieval V1 or production
search. Human query and relevance review is mandatory before benchmark evaluation.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
from PIL import Image

from sahulat_text.ingestion.khaadi.reader import KhaadiAuthority, load_khaadi_authority

from .config import Settings
from .domain import ImageRecord, ProductMatch, Vectors, normalize
from .encoders.base import VisualEncoder
from .encoders.factory import MODEL_SPECS
from .encoders.runtime import identity as make_identity
from .errors import ConfigurationError, ModelLoadError
from .index import InMemoryVectorIndex
from .io import content_hash, read_json, write_json
from .pipeline import embed_catalogue
from .retrieval import aggregate_products

PILOT_VERSION = "FASHIONCLIP-URDU-RETRIEVAL-PILOT-V1"
PILOT_ROOT = Path("artifacts/fashionclip_urdu_retrieval_pilot_v1")
QUERY_DATA = Path("data/fashionclip_urdu_retrieval_pilot_v1/queries.json")
QUERY_MANIFEST = Path("data/fashionclip_urdu_retrieval_pilot_v1/frozen_manifest.json")
INDEX_META_VERSION = 1
QUERY_COUNT = 30
TOP_K = 5
MODEL_NAMES = ("fashionclip", "openclip")
SCRIPT_PROFILES = {"urdu_script", "roman_urdu", "mixed_script"}
LANGUAGES = {"ur", "ur_en_mixed"}


class PilotBlockedError(RuntimeError):
    """A required pilot data, source, or local model gate is not satisfied."""


class DualEncoder(VisualEncoder):
    def encode_text(self, texts: Sequence[str]) -> Vectors:
        raise NotImplementedError


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise PilotBlockedError(f"Required local file is unavailable: {path}") from exc
    return digest.hexdigest()


def pilot_config(root: Path | None = None) -> dict[str, Any]:
    base = root or repository_root()
    config_path = base / "configs/fashionclip_urdu_retrieval_pilot_v1.json"
    try:
        config = read_json(config_path)
    except (OSError, ValueError, TypeError) as exc:
        raise PilotBlockedError(
            f"Pilot source/model registry is unavailable: {config_path}"
        ) from exc
    if (
        config.get("pilot_version") != PILOT_VERSION
        or config.get("models") != MODEL_SPECS
        or not isinstance(config.get("gallery"), dict)
        or any(
            config["gallery"].get(key) != value
            for key, value in {
                "fixture": "khaadi-v1",
                "products": 400,
                "retained_images": 2093,
            }.items()
        )
        or config.get("ranking")
        != {
            "embedding_normalization": "l2-float32-after-float64-norm",
            "similarity": "normalized-inner-product-cosine",
            "product_aggregation": "maximum-image-similarity",
            "ties": "product-id-then-image-id-ascending",
            "top_k": TOP_K,
        }
        or config.get("query_set", {}).get("required_count") != QUERY_COUNT
    ):
        raise PilotBlockedError("Pilot registry drifted from its pinned protocol")
    return config


def load_authority(root: Path | None = None) -> KhaadiAuthority:
    base = (root or repository_root()).resolve()
    try:
        authority = load_khaadi_authority(base, verify_image_binaries=True)
    except (OSError, ValueError, KeyError) as exc:
        raise PilotBlockedError(f"Khaadi V1 fixture authority check failed: {exc}") from exc
    if len(authority.valid_product_ids) != 400 or len(authority.visual_retained) != 2093:
        raise PilotBlockedError(
            "Khaadi gallery does not match the verified 400-product / 2,093-image fixture"
        )
    registry = pilot_config(base)["gallery"]
    if (
        registry.get("source_archive_sha256") != authority.source_sha256
        or registry.get("image_manifest_sha256") != authority.manifest_sha256
        or registry.get("visual_audit_sha256") != authority.visual_audit_sha256
    ):
        raise PilotBlockedError("Khaadi source checksums differ from the pilot-pinned registry")
    return authority


def source_identity(authority: KhaadiAuthority) -> dict[str, Any]:
    return {
        "fixture": "khaadi-v1",
        "dataset_version": authority.dataset_version,
        "source_sha256": authority.source_sha256,
        "manifest_sha256": authority.manifest_sha256,
        "visual_audit_sha256": authority.visual_audit_sha256,
        "products": len(authority.valid_product_ids),
        "retained_images": len(authority.visual_retained),
    }


class FashionCLIPDualEncoder(DualEncoder):
    """Loads the pinned FashionCLIP checkpoint for both CLIP towers, local-only."""

    def __init__(self, settings: Settings, spec: dict[str, str]) -> None:
        start = perf_counter()
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        try:
            import open_clip
            import torch
            from huggingface_hub import snapshot_download
            from transformers import CLIPImageProcessor, CLIPModel

            self.device = _device(settings.device, torch)
            snapshot = snapshot_download(
                spec["identifier"],
                revision=spec["revision"],
                cache_dir=settings.cache_dir,
                allow_patterns=["config.json", spec["weights_file"], "preprocessor_config.json"],
                local_files_only=True,
            )
            self._processor = CLIPImageProcessor.from_pretrained(snapshot, local_files_only=True)
            self._model = CLIPModel.from_pretrained(
                snapshot, local_files_only=True, use_safetensors=True
            ).to(self.device)
            self._tokenizer = open_clip.get_tokenizer(spec["architecture"])
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            raise ModelLoadError(
                "FashionCLIP dual encoder unavailable locally: expected cached "
                f"{spec['identifier']}@{spec['revision']} with CLIP image/text weights, "
                "Transformers image processor, PyTorch and open_clip_torch's OpenAI CLIP BPE"
            ) from exc
        self._model.eval().requires_grad_(False)
        processor_config = self._processor.to_dict()
        self.identity = make_identity(
            "fashionclip",
            spec,
            {
                "image_processor": processor_config,
                "text_tokenizer": "open_clip ViT-B-32 OpenAI CLIP byte-BPE; context=77",
                "dual_tower": "same pinned CLIPModel safetensors checkpoint",
            },
            self._model.config.projection_dim,
            ["transformers", "torch", "torchvision", "Pillow", "numpy", "open_clip_torch"],
        )
        self._torch = torch
        self.synchronize()
        self.load_time_ms = (perf_counter() - start) * 1000

    def encode_images(self, images: Sequence[Image.Image]) -> Vectors:
        if not images:
            return np.empty((0, self.embedding_dimension), dtype=np.float32)
        with self._torch.inference_mode():
            pixels = self._processor(
                images=[image.convert("RGB") for image in images], return_tensors="pt"
            )["pixel_values"].to(self.device)
            features = self._model.get_image_features(pixel_values=pixels)
            return normalize(features.float().cpu().numpy())

    def encode_text(self, texts: Sequence[str]) -> Vectors:
        if not texts:
            return np.empty((0, self.embedding_dimension), dtype=np.float32)
        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError("Text queries must be non-empty strings")
        with self._torch.inference_mode():
            tokens = self._tokenizer(list(texts)).to(self.device)
            features = self._model.get_text_features(input_ids=tokens)
            return normalize(features.float().cpu().numpy())

    def synchronize(self) -> None:
        _synchronize(self.device)


class OpenCLIPDualEncoder(DualEncoder):
    """Pilot wrapper around the existing pinned OpenCLIP encoder and text tower."""

    def __init__(self, settings: Settings, spec: dict[str, str]) -> None:
        from open_clip import get_tokenizer

        # Reuse the repository's verified OpenCLIP image preprocessing and weights.
        from .encoders.openclip_encoder import OpenCLIPEncoder

        image_encoder = OpenCLIPEncoder(settings, spec)
        self._model = image_encoder._model
        self._preprocess = image_encoder._preprocess
        self.device = image_encoder.device
        self.load_time_ms = image_encoder.load_time_ms
        self._tokenizer = get_tokenizer(spec["architecture"])
        self.identity = make_identity(
            "openclip",
            spec,
            {
                "image_encoder_preprocessing_identity": image_encoder.identity.preprocessing,
                "text_tokenizer": "open_clip ViT-B-32 OpenAI CLIP byte-BPE; context=77",
                "dual_tower": "same pinned OpenCLIP model checkpoint",
            },
            image_encoder.embedding_dimension,
            ["open_clip_torch", "torch", "torchvision", "Pillow", "numpy"],
        )

    def encode_images(self, images: Sequence[Image.Image]) -> Vectors:
        if not images:
            return np.empty((0, self.embedding_dimension), dtype=np.float32)
        import torch

        with torch.inference_mode():
            batch = torch.stack([self._model_transform(image) for image in images])
            features = self._model.encode_image(batch.to(self.device))
            return normalize(features.float().cpu().numpy())

    def _model_transform(self, image: Image.Image) -> Any:
        # open_clip model transform is attached during construction below.
        return self._preprocess(image.convert("RGB"))

    def encode_text(self, texts: Sequence[str]) -> Vectors:
        if not texts:
            return np.empty((0, self.embedding_dimension), dtype=np.float32)
        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError("Text queries must be non-empty strings")
        import torch

        with torch.inference_mode():
            tokens = self._tokenizer(list(texts)).to(self.device)
            features = self._model.encode_text(tokens)
            return normalize(features.float().cpu().numpy())

    def synchronize(self) -> None:
        _synchronize(self.device)


def _device(requested: str, torch: Any) -> str:
    if requested == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    try:
        selected = torch.device(requested)
        torch.empty(1, device=selected)
    except (RuntimeError, ValueError) as exc:
        raise ConfigurationError(f"Requested pilot device is unavailable: {requested}") from exc
    return str(selected)


def _synchronize(device: str) -> None:
    import torch

    if torch.device(device).type == "cuda":
        torch.cuda.synchronize(device)


def create_encoder(model_name: str, root: Path | None = None, device: str = "auto") -> DualEncoder:
    if model_name not in MODEL_NAMES:
        raise ConfigurationError(f"Unsupported pilot model: {model_name}")
    config = pilot_config(root)
    specs = config["models"]
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    settings = Settings(
        model=model_name,
        device=device,
        cache_dir=str((root or repository_root()) / ".cache/models"),
    )
    try:
        if model_name == "fashionclip":
            return FashionCLIPDualEncoder(settings, specs[model_name])
        encoder = OpenCLIPDualEncoder(settings, specs[model_name])
        # Resolve the existing image checkpoint with all hub access kept offline.
        return encoder
    except (OSError, ImportError, RuntimeError, ValueError) as exc:
        raise ModelLoadError(
            f"{model_name} pilot checkpoint is unavailable from the local pinned cache "
            f"({specs[model_name]['identifier']}@{specs[model_name]['revision']})"
        ) from exc


def records_from_authority(authority: KhaadiAuthority) -> list[ImageRecord]:
    return [
        ImageRecord(row["image_id"], row["product_id"], row["image_path"])
        for row in authority.visual_retained
    ]


def index_path(root: Path, model_name: str) -> Path:
    return root / PILOT_ROOT / f"{model_name}.index.npz"


def index_sidecar_path(root: Path, model_name: str) -> Path:
    return root / PILOT_ROOT / f"{model_name}.index.json"


def build_index(model_name: str, root: Path | None = None, device: str = "auto") -> dict[str, Any]:
    base = (root or repository_root()).resolve()
    pilot_config(base)
    authority = load_authority(base)
    encoder = create_encoder(model_name, base, device)
    records = records_from_authority(authority)
    expected_hashes = {row["image_id"]: row["pixel_sha256"] for row in authority.visual_retained}
    run = embed_catalogue(
        encoder,
        records,
        base / "data/raw/khaadi",
        batch_size=16,
        expected_hashes=expected_hashes,
    )
    metadata = {
        "pilot_version": PILOT_VERSION,
        "source": source_identity(authority),
        "model": model_name,
        "model_identity": encoder.identity.to_dict(),
        "registry_sha256": sha256_file(base / "configs/fashionclip_urdu_retrieval_pilot_v1.json"),
        "normalization": "L2 per image and query; float64 norm; float32 output",
        "gallery": {"images": len(records), "products": 400},
        "image_embedding_ms": run.total_ms,
    }
    index = InMemoryVectorIndex(encoder.identity, run.vectors, records, metadata)
    artifact = index_path(base, model_name)
    sidecar = index_sidecar_path(base, model_name)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    if artifact.exists() or sidecar.exists():
        raise PilotBlockedError(
            f"Pilot index already exists; refusing implicit replacement: {artifact}. "
            "Move it aside after review before rebuilding."
        )
    index.save(artifact)
    evidence = {
        "format_version": INDEX_META_VERSION,
        "artifact_sha256": sha256_file(artifact),
        "metadata": metadata,
    }
    write_json(sidecar, evidence)
    return {
        "model": model_name,
        "index": str(artifact.relative_to(base)),
        "sha256": evidence["artifact_sha256"],
        "images": index.count,
        "products": 400,
        "embedding_ms": round(run.total_ms, 3),
        "status": "BUILT",
    }


def load_index(model_name: str, root: Path | None = None) -> InMemoryVectorIndex:
    base = (root or repository_root()).resolve()
    authority = load_authority(base)
    artifact = index_path(base, model_name)
    sidecar = index_sidecar_path(base, model_name)
    if not artifact.is_file() or not sidecar.is_file():
        raise PilotBlockedError(
            f"Missing local {model_name} pilot image index; run build-index first ({artifact})"
        )
    try:
        evidence = read_json(sidecar)
    except (OSError, ValueError, TypeError) as exc:
        raise PilotBlockedError(f"Invalid index sidecar: {sidecar}") from exc
    if evidence.get("artifact_sha256") != sha256_file(artifact):
        raise PilotBlockedError(f"Pilot index checksum drift detected: {artifact}")
    metadata = evidence.get("metadata", {})
    if evidence.get("format_version") != INDEX_META_VERSION:
        raise PilotBlockedError("Unsupported pilot index sidecar format")
    if metadata.get("pilot_version") != PILOT_VERSION:
        raise PilotBlockedError("Pilot index belongs to another protocol version")
    if metadata.get("source") != source_identity(authority):
        raise PilotBlockedError("Pilot index source identity drifted or is not authorized")
    if metadata.get("model") != model_name:
        raise PilotBlockedError("Pilot index model identity drifted")
    if metadata.get("registry_sha256") != sha256_file(
        base / "configs/fashionclip_urdu_retrieval_pilot_v1.json"
    ):
        raise PilotBlockedError("Pilot model registry changed after index build")
    try:
        index = InMemoryVectorIndex.load(artifact)
    except (OSError, ValueError) as exc:
        raise PilotBlockedError(f"Cannot load pilot index: {artifact}") from exc
    if (
        index.count != 2093
        or index.identity.to_dict() != metadata.get("model_identity")
        or index.metadata != metadata
    ):
        raise PilotBlockedError("Pilot index contents differ from their frozen sidecar")
    return index


def annotation_template() -> dict[str, Any]:
    return {
        "pilot_version": PILOT_VERSION,
        "status": "DRAFT",
        "queries": [
            {
                "query_id": f"UR-{number:03d}",
                "language": None,
                "script_profile": None,
                "urdu_query": None,
                "roman_urdu_transliteration": None,
                "english_reference": None,
                "translation_review": {
                    "status": "PENDING",
                    "reviewer": None,
                    "reviewed_at": None,
                },
                "relevant_product_ids": [],
                "relevance_review": {
                    "status": "PENDING",
                    "reviewer": None,
                    "reviewed_at": None,
                },
                "commerce_reference": None,
            }
            for number in range(1, QUERY_COUNT + 1)
        ],
    }


def ensure_query_template(root: Path | None = None) -> Path:
    base = root or repository_root()
    path = base / QUERY_DATA
    if not path.exists():
        write_json(path, annotation_template())
    return path


def _valid_review(value: Any) -> bool:
    if not isinstance(value, dict) or value.get("status") != "VERIFIED":
        return False
    reviewer = value.get("reviewer")
    reviewed_at = value.get("reviewed_at")
    if not isinstance(reviewer, str) or not reviewer.strip() or not isinstance(reviewed_at, str):
        return False
    try:
        date.fromisoformat(reviewed_at)
    except ValueError:
        return False
    return True


def validate_queries(queries: Any, valid_product_ids: set[str] | frozenset[str]) -> list[str]:
    errors: list[str] = []
    if not isinstance(queries, list) or len(queries) != QUERY_COUNT:
        return [f"expected exactly {QUERY_COUNT} query records"]
    seen: set[str] = set()
    for position, query in enumerate(queries):
        prefix = f"queries[{position}]"
        if not isinstance(query, dict):
            errors.append(f"{prefix} must be an object")
            continue
        query_id = query.get("query_id")
        if not isinstance(query_id, str) or not re.fullmatch(r"UR-\d{3}", query_id):
            errors.append(f"{prefix}.query_id must use UR-NNN format")
        elif query_id in seen:
            errors.append(f"{prefix}.query_id is duplicated: {query_id}")
        else:
            seen.add(query_id)
        if query.get("language") not in LANGUAGES:
            errors.append(f"{prefix}.language must be ur or ur_en_mixed")
        if query.get("script_profile") not in SCRIPT_PROFILES:
            errors.append(f"{prefix}.script_profile must identify the Urdu script profile")
        if not isinstance(query.get("urdu_query"), str) or not query["urdu_query"].strip():
            errors.append(f"{prefix}.urdu_query is missing")
        if (
            not isinstance(query.get("english_reference"), str)
            or not query["english_reference"].strip()
        ):
            errors.append(f"{prefix}.english_reference is missing")
        if query.get("script_profile") in {"roman_urdu", "mixed_script"} and not (
            isinstance(query.get("roman_urdu_transliteration"), str)
            and query["roman_urdu_transliteration"].strip()
        ):
            errors.append(
                f"{prefix}.roman_urdu_transliteration is required for this script profile"
            )
        if not _valid_review(query.get("translation_review")):
            errors.append(f"{prefix}.english_reference is not human-verified")
        if not _valid_review(query.get("relevance_review")):
            errors.append(f"{prefix}.relevant_product_ids are not human-verified")
        ids = query.get("relevant_product_ids")
        if not isinstance(ids, list) or not ids or any(not isinstance(pid, str) for pid in ids):
            errors.append(f"{prefix}.relevant_product_ids must be a non-empty list")
        else:
            if len(ids) != len(set(ids)):
                errors.append(f"{prefix}.relevant_product_ids contains duplicates")
            for product_id in ids:
                if product_id not in valid_product_ids:
                    errors.append(f"{prefix} references product outside gallery: {product_id}")
        if query.get("commerce_reference") is not None and not isinstance(
            query.get("commerce_reference"), dict
        ):
            errors.append(f"{prefix}.commerce_reference must be an object or null")
    expected_ids = {f"UR-{number:03d}" for number in range(1, QUERY_COUNT + 1)}
    if seen != expected_ids:
        errors.append("query IDs must be the complete deterministic UR-001 through UR-030 set")
    return errors


def freeze_query_manifest(root: Path | None = None) -> dict[str, Any]:
    base = root or repository_root()
    authority = load_authority(base)
    source = ensure_query_template(base)
    try:
        payload = read_json(source)
    except (OSError, ValueError, TypeError) as exc:
        raise PilotBlockedError(f"Cannot read query annotation file: {source}") from exc
    if payload.get("pilot_version") != PILOT_VERSION:
        raise PilotBlockedError("Query annotation file belongs to a different pilot version")
    errors = validate_queries(payload.get("queries"), authority.valid_product_ids)
    if errors:
        raise PilotBlockedError("Query freeze blocked: " + "; ".join(errors[:12]))
    canonical = {
        "pilot_version": PILOT_VERSION,
        "query_count": QUERY_COUNT,
        "source": source_identity(authority),
        "queries": payload["queries"],
    }
    manifest = {**canonical, "manifest_sha256": content_hash(canonical)}
    path = base / QUERY_MANIFEST
    if path.exists():
        current = read_json(path)
        verify_query_manifest(current, payload["queries"], authority)
        if current != manifest:
            raise PilotBlockedError(
                "Frozen query manifest differs; create a versioned amendment "
                "instead of replacing it"
            )
    else:
        write_json(path, manifest)
    return manifest


def verify_query_manifest(
    manifest: Any, current_queries: Any | None = None, authority: KhaadiAuthority | None = None
) -> None:
    if not isinstance(manifest, dict) or manifest.get("pilot_version") != PILOT_VERSION:
        raise PilotBlockedError("Frozen query manifest is missing or belongs to another pilot")
    canonical = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if manifest.get("manifest_sha256") != content_hash(canonical):
        raise PilotBlockedError("Frozen query manifest checksum drift detected")
    if current_queries is not None and canonical.get("queries") != current_queries:
        raise PilotBlockedError("Query annotations changed after freeze")
    if authority is not None:
        if canonical.get("source") != source_identity(authority):
            raise PilotBlockedError("Frozen query manifest source identity drifted")
        errors = validate_queries(canonical.get("queries"), authority.valid_product_ids)
        if errors:
            raise PilotBlockedError("Frozen query manifest invalid: " + "; ".join(errors[:12]))


def load_frozen_queries(root: Path | None = None) -> tuple[dict[str, Any], KhaadiAuthority]:
    base = root or repository_root()
    authority = load_authority(base)
    try:
        manifest = read_json(base / QUERY_MANIFEST)
        raw = read_json(base / QUERY_DATA)
    except (OSError, ValueError, TypeError) as exc:
        raise PilotBlockedError(
            "Human query annotations are unavailable; populate the 30-row template, "
            "complete human reviews, then freeze it"
        ) from exc
    verify_query_manifest(manifest, raw.get("queries"), authority)
    return manifest, authority


def rank_query(
    encoder: DualEncoder, index: InMemoryVectorIndex, text: str
) -> tuple[list[ProductMatch], float]:
    started = perf_counter()
    vector = encoder.encode_text([text])[0]
    neighbors = index.search(vector, index.count, encoder.identity)
    products = aggregate_products(neighbors, TOP_K)
    encoder.synchronize()
    return products, (perf_counter() - started) * 1000


def retrieval_metrics(
    ranked_ids: Sequence[str], relevant_ids: set[str] | frozenset[str]
) -> dict[str, float]:
    if not relevant_ids:
        raise ValueError("At least one relevant product is required")
    top = list(ranked_ids[:TOP_K])
    hits = [product_id in relevant_ids for product_id in top]
    dcg = sum(1 / math.log2(position + 2) for position, hit in enumerate(hits) if hit)
    ideal_hits = min(TOP_K, len(relevant_ids))
    ideal = sum(1 / math.log2(position + 2) for position in range(ideal_hits))
    return {
        "precision_at_1": float(bool(hits and hits[0])),
        "recall_at_5": sum(hits) / len(relevant_ids),
        "ndcg_at_5": dcg / ideal if ideal else 0.0,
    }


def _query_result(
    query: dict[str, Any],
    model_name: str,
    ranked: list[ProductMatch],
    latency_ms: float,
    search_text: str,
    track: str,
) -> dict[str, Any]:
    relevant = set(query["relevant_product_ids"])
    ranked_ids = [match.product_id for match in ranked]
    metrics = retrieval_metrics(ranked_ids, relevant)
    return {
        "query_id": query["query_id"],
        "language": query["language"],
        "script_profile": query["script_profile"],
        "original_urdu_query": query["urdu_query"],
        "english_query": query["english_reference"],
        "search_text": search_text,
        "track": track,
        "model": model_name,
        "top_5": [
            {
                "rank": rank,
                "product_id": match.product_id,
                "matched_image_id": match.matched_image_id,
                "matched_image_path": match.matched_image_path,
                "similarity": match.score,
                "relevant": match.product_id in relevant,
            }
            for rank, match in enumerate(ranked, 1)
        ],
        "metrics": metrics,
        "latency_ms": latency_ms,
        "error": {
            "false_positive_product_ids": [pid for pid in ranked_ids if pid not in relevant],
            "relevant_not_retrieved": sorted(relevant - set(ranked_ids)),
        },
        "commerce_extraction": "NOT_EVALUATED_NO_COMMERCE_EXTRACTOR_IN_SCOPE",
        "commerce_reference": query.get("commerce_reference"),
    }


def evaluate(root: Path | None = None, models: Sequence[str] = MODEL_NAMES) -> dict[str, Any]:
    base = root or repository_root()
    manifest, authority = load_frozen_queries(base)
    outputs: dict[str, Any] = {}
    for model_name in models:
        index = load_index(model_name, base)
        encoder = create_encoder(model_name, base)
        if encoder.identity != index.identity:
            raise PilotBlockedError(
                f"Loaded {model_name} checkpoint/tokenizer identity differs from index"
            )
        results: list[dict[str, Any]] = []
        for query in manifest["queries"]:
            tracks: list[tuple[str, str]] = [
                ("english_reference", query["english_reference"]),
                ("urdu_direct", query["urdu_query"]),
            ]
            translation = None
            translation_config = read_json(base / "configs/fashionclip_urdu_translation_v1.json")
            if model_name == "fashionclip" and translation_config.get("enabled"):
                try:
                    translation = translate_urdu(query["urdu_query"], base)
                    tracks.append(("translation_adapter", translation))
                except Exception as exc:
                    results.append(
                        {
                            "query_id": query["query_id"],
                            "language": query["language"],
                            "script_profile": query["script_profile"],
                            "original_urdu_query": query["urdu_query"],
                            "english_query": None,
                            "search_text": None,
                            "track": "translation_adapter",
                            "model": model_name,
                            "top_5": [],
                            "metrics": None,
                            "latency_ms": None,
                            "error": {"type": type(exc).__name__, "message": str(exc)},
                        }
                    )
            for track, text in tracks:
                try:
                    ranked, latency_ms = rank_query(encoder, index, text)
                    row = _query_result(query, model_name, ranked, latency_ms, text, track)
                    row["english_query"] = (
                        translation
                        if track == "translation_adapter"
                        else query["english_reference"]
                    )
                    if track == "translation_adapter" and translation is not None:
                        row["translation_metrics"] = translation_metrics(
                            translation, query["english_reference"]
                        )
                    results.append(row)
                except Exception as exc:  # Keep individual inference failures auditable.
                    results.append(
                        {
                            "query_id": query["query_id"],
                            "language": query["language"],
                            "script_profile": query["script_profile"],
                            "original_urdu_query": query["urdu_query"],
                            "english_query": query["english_reference"],
                            "search_text": text,
                            "track": track,
                            "model": model_name,
                            "top_5": [],
                            "metrics": None,
                            "latency_ms": None,
                            "error": {"type": type(exc).__name__, "message": str(exc)},
                        }
                    )
        track_names = sorted({row["track"] for row in results})
        outputs[model_name] = {
            "tracks": {
                track: _summarize_model([row for row in results if row["track"] == track])
                for track in track_names
            },
            "queries": results,
        }
    summary = {
        "pilot_version": PILOT_VERSION,
        "evaluation_status": "PILOT",
        "query_manifest_sha256": manifest["manifest_sha256"],
        "source": source_identity(authority),
        "gallery": {"products": 400, "images": 2093},
        "query_count": QUERY_COUNT,
        "speaker_count": (
            "NOT_APPLICABLE_TO_PRODUCT-QUERY RETRIEVAL; no speaker identities collected"
        ),
        "models": outputs,
        "strongest_existing_model_per_language": _winners(outputs),
        "release_warning": "Pilot-only; not production-grade and does not replace EVAL-VISUAL-V1.",
    }
    report_dir = base / PILOT_ROOT
    report_dir.mkdir(parents=True, exist_ok=True)
    write_json(report_dir / "evaluation.json", summary)
    write_json(report_dir / "evaluation_queries.json", outputs)
    (report_dir / "evaluation.md").write_text(render_report(summary), encoding="utf-8")
    return summary


def _summarize_model(results: list[dict[str, Any]]) -> dict[str, Any]:
    languages = sorted({result["language"] for result in results})
    by_language = {
        language: _aggregate_queries(
            [result for result in results if result["language"] == language]
        )
        for language in languages
    }
    return {
        **_aggregate_queries(results),
        "by_language": by_language,
        "speaker_count": "NOT_COLLECTED",
        "queries": results,
    }


def _aggregate_queries(results: list[dict[str, Any]]) -> dict[str, Any]:
    successful = [result for result in results if result["metrics"] is not None]
    count = len(results)
    metrics = ("precision_at_1", "recall_at_5", "ndcg_at_5")
    return {
        "query_count": count,
        "failed_query_count": count - len(successful),
        "failed_query_rate": (count - len(successful)) / count if count else 0.0,
        "aggregate": {
            key: sum(result["metrics"][key] for result in successful) / len(successful)
            if successful
            else None
            for key in metrics
        },
        "mean_latency_ms": (
            sum(result["latency_ms"] for result in successful) / len(successful)
            if successful
            else None
        ),
    }


def _winners(models: dict[str, Any]) -> dict[str, str | None]:
    languages = sorted(
        {query["language"] for model in models.values() for query in model["queries"]}
    )
    winners: dict[str, str | None] = {}
    for language in languages:
        candidates = []
        for model_name, model in models.items():
            results = [
                row
                for row in model["queries"]
                if row["language"] == language
                and row["track"] == "english_reference"
                and row["metrics"]
            ]
            if results:
                candidates.append(
                    (
                        sum(row["metrics"]["ndcg_at_5"] for row in results) / len(results),
                        sum(row["metrics"]["recall_at_5"] for row in results) / len(results),
                        sum(row["metrics"]["precision_at_1"] for row in results) / len(results),
                        model_name,
                    )
                )
        if not candidates:
            winners[language] = None
            continue
        best_score = max(candidate[:3] for candidate in candidates)
        leaders = sorted(candidate[3] for candidate in candidates if candidate[:3] == best_score)
        winners[language] = leaders[0] if len(leaders) == 1 else f"tie: {', '.join(leaders)}"
    return winners


def render_report(summary: dict[str, Any]) -> str:
    lines = [
        "# FashionCLIP Urdu Retrieval Pilot V1",
        "",
        "Status: **PILOT**. This report is not production-grade and does not replace "
        "EVAL-VISUAL-V1.",
        "",
        f"Human-reviewed queries: {summary['query_count']}",
        f"Gallery: {summary['gallery']['products']} products / "
        f"{summary['gallery']['images']} retained images.",
        "",
        "| Model / track / language | Queries | P@1 | Recall@5 | nDCG@5 | "
        "Failed query rate | Mean latency (ms) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for model_name, model in summary["models"].items():
        for track_name, track in model["tracks"].items():
            groups = [("ALL", track), *sorted(track["by_language"].items())]
            for language, metrics in groups:
                values = [
                    metrics["aggregate"][key]
                    for key in ("precision_at_1", "recall_at_5", "ndcg_at_5")
                ]
                lines.append(
                    f"| {model_name} / {track_name} / {language} | "
                    f"{metrics['query_count']} | "
                    + " | ".join("n/a" if value is None else f"{value:.4f}" for value in values)
                    + f" | {metrics['failed_query_rate']:.4f} | "
                    + (
                        "n/a"
                        if metrics["mean_latency_ms"] is None
                        else f"{metrics['mean_latency_ms']:.2f}"
                    )
                    + " |"
                )
    lines.extend(
        [
            "",
            "Strongest existing model by language (nDCG@5, then Recall@5, then P@1):",
            "",
        ]
    )
    lines.extend(
        f"- {language}: {model or 'no successful results'}"
        for language, model in summary["strongest_existing_model_per_language"].items()
    )
    lines.extend(
        [
            "",
            "Query-level rankings and error examples are in `evaluation_queries.json`.",
            "Commerce intent/brand/price extraction is not run because this pilot has no "
            "commerce extractor.",
            "Speaker counts do not apply: this is product-query retrieval, not a "
            "speech-speaker evaluation.",
            "",
        ]
    )
    return "\n".join(lines)


def search(
    model_name: str,
    urdu_query: str,
    english_query: str | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    if not isinstance(urdu_query, str) or not urdu_query.strip():
        raise ValueError("Original Urdu query is required")
    base = root or repository_root()
    index = load_index(model_name, base)
    encoder = create_encoder(model_name, base)
    if encoder.identity != index.identity:
        raise PilotBlockedError("Loaded checkpoint/tokenizer identity differs from pilot index")
    return search_with_loaded_encoder(model_name, encoder, index, urdu_query, english_query, base)


def search_with_loaded_encoder(
    model_name: str,
    encoder: DualEncoder,
    index: InMemoryVectorIndex,
    urdu_query: str,
    english_query: str | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    if not isinstance(urdu_query, str) or not urdu_query.strip():
        raise ValueError("Original Urdu query is required")
    if encoder.identity != index.identity:
        raise PilotBlockedError("Loaded checkpoint/tokenizer identity differs from pilot index")
    base = root or repository_root()
    config = read_json(base / "configs/fashionclip_urdu_translation_v1.json")
    translated: str | None = None
    if english_query is None and config.get("enabled"):
        translated = translate_urdu(urdu_query, base)
    search_text = english_query or translated or urdu_query
    ranked, latency = rank_query(encoder, index, search_text)
    return {
        "pilot_version": PILOT_VERSION,
        "evaluation_status": "EXPLORATORY_NOT_BENCHMARKED",
        "model": model_name,
        "original_urdu_query": urdu_query,
        "english_query": english_query or translated,
        "english_query_source": (
            "user_supplied_reference"
            if english_query
            else "local_translation_adapter"
            if translated
            else None
        ),
        "search_text": search_text,
        "top_5": [
            {
                "rank": rank,
                "product_id": match.product_id,
                "matched_image_id": match.matched_image_id,
                "image_path": match.matched_image_path,
                "similarity": match.score,
            }
            for rank, match in enumerate(ranked, 1)
        ],
        "latency_ms": latency,
    }


def translate_urdu(text: str, root: Path | None = None) -> str:
    base = root or repository_root()
    config_path = base / "configs/fashionclip_urdu_translation_v1.json"
    config = read_json(config_path)
    required = (config.get("model_id"), config.get("revision"))
    if not config.get("enabled") or not all(isinstance(value, str) and value for value in required):
        raise PilotBlockedError(
            "Urdu-to-English translation is disabled; set a separately approved model_id and "
            "40-character pinned revision in fashionclip_urdu_translation_v1.json"
        )
    if not re.fullmatch(r"[0-9a-f]{40}", config["revision"]):
        raise PilotBlockedError(
            "Translation adapter revision must be an immutable 40-character commit"
        )
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    try:
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(
            config["model_id"], revision=config["revision"], local_files_only=True
        )
        model = AutoModelForSeq2SeqLM.from_pretrained(
            config["model_id"], revision=config["revision"], local_files_only=True
        ).eval()
        tokenizer.src_lang = config.get("source_language_code", "urd_Arab")
        encoded = tokenizer(text, return_tensors="pt", truncation=True, max_length=256)
        forced_bos = tokenizer.convert_tokens_to_ids(config.get("target_language_code", "eng_Latn"))
        if forced_bos is None or forced_bos == tokenizer.unk_token_id:
            raise PilotBlockedError(
                "Configured translation model does not expose the target language token"
            )
        with torch.inference_mode():
            generated = model.generate(
                **encoded, forced_bos_token_id=forced_bos, max_new_tokens=128
            )
        result = tokenizer.batch_decode(generated, skip_special_tokens=True)[0].strip()
    except PilotBlockedError:
        raise
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        raise PilotBlockedError(
            "Configured translation checkpoint unavailable locally: "
            f"{config['model_id']}@{config['revision']}"
        ) from exc
    if not result:
        raise PilotBlockedError("Translation adapter returned an empty English query")
    return result


def translation_metrics(prediction: str, reference: str) -> dict[str, float | bool]:
    """Surface-form translation comparison only; does not imply semantic equivalence."""
    predicted = _translation_tokens(prediction)
    expected = _translation_tokens(reference)
    distance = _edit_distance(predicted, expected)
    denominator = max(1, len(expected))
    char_distance = _edit_distance(list(" ".join(predicted)), list(" ".join(expected)))
    char_denominator = max(1, len(" ".join(expected)))
    return {
        "exact_match": predicted == expected,
        "word_error_rate": distance / denominator,
        "character_error_rate": char_distance / char_denominator,
    }


def _translation_tokens(text: str) -> list[str]:
    return re.findall(r"[\w]+", text.casefold(), flags=re.UNICODE)


def _edit_distance(left: Sequence[Any], right: Sequence[Any]) -> int:
    previous = list(range(len(right) + 1))
    for row, item in enumerate(left, 1):
        current = [row]
        for column, expected in enumerate(right, 1):
            current.append(
                min(
                    previous[column] + 1,
                    current[column - 1] + 1,
                    previous[column - 1] + (item != expected),
                )
            )
        previous = current
    return previous[-1]


def status(root: Path | None = None) -> dict[str, Any]:
    base = root or repository_root()
    authority = load_authority(base)
    queries = ensure_query_template(base)
    payload = read_json(queries)
    errors = validate_queries(payload.get("queries"), authority.valid_product_ids)
    indexes = {
        name: {
            "present": index_path(base, name).is_file()
            and index_sidecar_path(base, name).is_file(),
            "path": str(index_path(base, name).relative_to(base)),
        }
        for name in MODEL_NAMES
    }
    result = {
        "pilot_version": PILOT_VERSION,
        "status": "PILOT",
        "source": source_identity(authority),
        "local_checkpoints": {name: _checkpoint_present(base, name) for name in MODEL_NAMES},
        "indexes": indexes,
        "query_template": str(queries.relative_to(base)),
        "query_annotation_error_count": len(errors),
        "query_annotation_errors": errors[:10],
        "query_annotation_errors_truncated": len(errors) > 10,
        "evaluation_ready": not errors and (base / QUERY_MANIFEST).is_file(),
        "remaining_blockers": (
            []
            if not errors and (base / QUERY_MANIFEST).is_file()
            else [
                "30 queries need human-verified translations and relevance judgments, then freeze"
            ]
        ),
    }
    report_dir = base / PILOT_ROOT
    report_dir.mkdir(parents=True, exist_ok=True)
    write_json(report_dir / "pilot_status.json", result)
    (report_dir / "pilot_status.md").write_text(_render_status_report(result), encoding="utf-8")
    return result


def _render_status_report(result: dict[str, Any]) -> str:
    lines = [
        "# FashionCLIP Urdu Retrieval Pilot V1 — Readiness",
        "",
        "Status: **PILOT**; this is not production-grade and does not replace "
        "frozen visual evidence.",
        "",
        f"Khaadi gallery: {result['source']['products']} products / "
        f"{result['source']['retained_images']} audited images.",
        "",
        "| Model | Local checkpoint | Pilot index |",
        "|---|---|---|",
    ]
    for name in MODEL_NAMES:
        lines.append(
            f"| {name} | {result['local_checkpoints'][name]} | "
            f"{result['indexes'][name]['present']} |"
        )
    lines.extend(
        [
            "",
            "Unmet checks in the currently blank human annotation template: "
            f"{result['query_annotation_error_count']}.",
            "",
            "Evaluation status: **BLOCKED** until 30 Urdu commerce queries have "
            "human-verified English counterparts and human-verified relevant product IDs, "
            "then are frozen.",
            "",
            "No retrieval scores or model winner have been generated. Do not interpret "
            "exploratory demo output as benchmark evidence.",
            "",
        ]
    )
    return "\n".join(lines)


def _checkpoint_present(root: Path, model_name: str) -> bool:
    spec = MODEL_SPECS[model_name]
    snapshot = (
        root
        / ".cache/models"
        / f"models--{spec['identifier'].replace('/', '--')}"
        / "snapshots"
        / spec["revision"]
    )
    expected = [spec["weights_file"]]
    expected.append(
        "preprocessor_config.json" if model_name == "fashionclip" else "open_clip_config.json"
    )
    return snapshot.is_dir() and all((snapshot / name).is_file() for name in expected)


def verify_artifact_integrity(root: Path | None = None) -> dict[str, Any]:
    base = root or repository_root()
    report: dict[str, Any] = {"pilot_version": PILOT_VERSION, "indexes": {}}
    for model_name in MODEL_NAMES:
        artifact = index_path(base, model_name)
        sidecar = index_sidecar_path(base, model_name)
        if not artifact.exists() or not sidecar.exists():
            report["indexes"][model_name] = {"status": "PENDING", "missing": str(artifact)}
            continue
        evidence = read_json(sidecar)
        actual = sha256_file(artifact)
        ok = actual == evidence.get("artifact_sha256")
        if not ok:
            raise PilotBlockedError(f"Pilot index checksum drift detected: {artifact}")
        index = load_index(model_name, base)
        report["indexes"][model_name] = {
            "status": "VERIFIED",
            "expected_sha256": evidence.get("artifact_sha256"),
            "actual_sha256": actual,
            "images": index.count,
            "products": len(index_gallery_products(index)),
            "checkpoint_revision": index.identity.model_version,
        }
    return report


def compare_translation_adapter(
    root: Path | None = None, model_name: str = "fashionclip"
) -> dict[str, Any]:
    base = root or repository_root()
    translator_config = read_json(base / "configs/fashionclip_urdu_translation_v1.json")
    if not translator_config.get("enabled"):
        raise PilotBlockedError(
            "Translation adapter evaluation is disabled until a real locally cached "
            "checkpoint and immutable revision are configured"
        )
    manifest, authority = load_frozen_queries(base)
    index = load_index(model_name, base)
    encoder = create_encoder(model_name, base)
    rows = []
    for query in manifest["queries"]:
        try:
            translation = translate_urdu(query["urdu_query"], base)
            ranked, latency = rank_query(encoder, index, translation)
            rows.append(
                {
                    "query_id": query["query_id"],
                    "translation": translation,
                    "translation_metrics": translation_metrics(
                        translation, query["english_reference"]
                    ),
                    "retrieval": _query_result(query, model_name, ranked, latency, translation),
                }
            )
        except Exception as exc:
            rows.append({"query_id": query["query_id"], "error": f"{type(exc).__name__}: {exc}"})
    successful = [row for row in rows if "translation_metrics" in row]
    result = {
        "pilot_version": PILOT_VERSION,
        "status": "PILOT",
        "model": model_name,
        "translation_checkpoint": {
            "model_id": translator_config.get("model_id"),
            "revision": translator_config.get("revision"),
        },
        "query_manifest_sha256": manifest["manifest_sha256"],
        "source": source_identity(authority),
        "summary": {
            "query_count": len(rows),
            "failed_query_count": len(rows) - len(successful),
            "exact_match_rate": (
                sum(bool(row["translation_metrics"]["exact_match"]) for row in successful)
                / len(successful)
                if successful
                else None
            ),
            "mean_word_error_rate": (
                sum(float(row["translation_metrics"]["word_error_rate"]) for row in successful)
                / len(successful)
                if successful
                else None
            ),
            "mean_character_error_rate": (
                sum(float(row["translation_metrics"]["character_error_rate"]) for row in successful)
                / len(successful)
                if successful
                else None
            ),
        },
        "queries": rows,
    }
    report_path = base / PILOT_ROOT / "translation_adapter_evaluation.json"
    write_json(report_path, result)
    return result


def index_gallery_products(index: InMemoryVectorIndex) -> set[str]:
    return {record.product_id for record in index._records}
