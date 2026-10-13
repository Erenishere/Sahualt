import importlib.metadata
import logging
import os
import platform
import random
import subprocess
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np

from ..config import Settings
from ..dataset import records_from_audit, resolve_image, verify_split
from ..encoders.base import VisualEncoder
from ..encoders.factory import create_encoder
from ..errors import DatasetError
from ..images import load_image, pixel_hash
from ..index import InMemoryVectorIndex
from ..io import content_hash, read_json, write_json
from ..pipeline import embed_catalogue
from ..retrieval import aggregate_products
from .metrics import query_metrics, relevance
from .protocol import audit_protocol, config_path, image_policy, load_protocol


def latency_summary(samples: list[float]) -> dict[str, float]:
    if not samples:
        raise ValueError("Cannot summarize empty latency samples")
    return {
        "mean_ms": float(np.mean(samples)),
        "median_ms": float(np.median(samples)),
        "p50_ms": float(np.percentile(samples, 50)),
        "p95_ms": float(np.percentile(samples, 95)),
    }


def runtime_metadata(encoder: VisualEncoder, seed: int) -> dict[str, Any]:
    try:
        git = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5, check=False
        )
        commit = git.stdout.strip() if git.returncode == 0 else None
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, timeout=5, check=False
        )
        git_dirty = bool(dirty.stdout.strip()) if dirty.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        commit, git_dirty = None, None
    packages = {}
    for package in (
        "numpy",
        "Pillow",
        "torch",
        "torchvision",
        "open_clip_torch",
        "transformers",
        "huggingface_hub",
        "safetensors",
        "timm",
    ):
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = "not-installed"
    result = {
        "timestamp": datetime.now(UTC).isoformat(),
        "git_commit": commit,
        "git_dirty": git_dirty,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "processor": platform.processor(),
        "packages": packages,
        "device": encoder.device,
        "seed": seed,
        "source_sha256": content_hash(
            {
                str(p.relative_to(Path(__file__).parents[1])): p.read_text(encoding="utf-8")
                for p in sorted(Path(__file__).parents[1].rglob("*.py"))
            }
        ),
    }
    try:
        import torch

        result["torch_threads"] = torch.get_num_threads()
        result["cuda_version"] = torch.version.cuda
        if encoder.device.startswith("cuda"):
            result["gpu"] = torch.cuda.get_device_name(encoder.device)
            result["peak_cuda_allocated_bytes"] = torch.cuda.max_memory_allocated(encoder.device)
    except ImportError:
        pass  # Lightweight integration tests deliberately run without torch.
    return result


def seed_runtime(seed: int) -> None:
    # Must be set before CUDA context creation for deterministic GEMM.
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    random.seed(seed)
    np.random.seed(seed)
    import torch

    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.benchmark = False
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False


def evaluate(
    encoder: VisualEncoder,
    config: dict[str, Any],
    config_file: Path,
    audit: dict[str, Any],
    split: dict[str, Any],
    output: Path,
) -> dict[str, Any]:
    verify_split(split, audit, config)
    root = config_path(config_file, config["dataset"]["root"])
    policy = image_policy(config)
    gallery = records_from_audit(audit, split["gallery_ids"])
    queries = records_from_audit(audit, split["query_ids"])
    expected_hashes = {r["image_id"]: r["pixel_sha256"] for r in audit["retained"]}
    for row in queries[: config["runtime"]["warmup_images"]]:
        with load_image(resolve_image(root, row.image_path), policy) as image:
            encoder.encode_image(image)
    encoder.synchronize()
    embedded = embed_catalogue(
        encoder,
        gallery,
        root,
        config["runtime"]["batch_size"],
        config["runtime"]["num_workers"],
        policy,
        expected_hashes,
    )
    index = InMemoryVectorIndex(
        encoder.identity,
        embedded.vectors,
        gallery,
        {
            "dataset": config["dataset"]["source"],
            "dataset_version": config["dataset"]["version"],
            "split_sha256": split["split_sha256"],
            "created_at": datetime.now(UTC).isoformat(),
        },
    )
    totals = Counter(row.product_id for row in gallery)
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    query_times, search_times, e2e_times = [], [], []
    for query_number, row in enumerate(queries, 1):
        start = perf_counter()
        with load_image(resolve_image(root, row.image_path), policy) as image:
            if pixel_hash(image) != expected_hashes[row.image_id]:
                raise DatasetError(f"Query changed after audit: {row.image_id}")
            vector = encoder.encode_image(image)
        encoder.synchronize()
        query_ms = (perf_counter() - start) * 1000
        search_start = perf_counter()
        # Full ranking is necessary for uncensored MRR and exact deterministic image metrics.
        matches = index.search(vector, index.count, encoder.identity)
        search_ms = (perf_counter() - search_start) * 1000
        products = aggregate_products(matches, 5)
        e2e_ms = (perf_counter() - start) * 1000
        relevant = relevance(row.product_id, [m.record.product_id for m in matches])
        metrics = query_metrics(relevant, totals[row.product_id])
        example = {
            "query": asdict(row),
            "metrics": metrics,
            "top_images": [{**asdict(m.record), "score": m.score} for m in matches[:5]],
            "top_products": [asdict(p) for p in products],
            "query_embedding_ms": query_ms,
            "search_ms": search_ms,
            "e2e_ms": e2e_ms,
        }
        rows.append(example)
        query_times.append(query_ms)
        search_times.append(search_ms)
        e2e_times.append(e2e_ms)
        if metrics["precision_at_1"] < 1 or metrics["recall_at_5"] < 1:
            failures.append(
                {**example, "review_status": "unreviewed", "categories": [], "evidence": None}
            )
        if query_number % 50 == 0 or query_number == len(queries):
            logging.getLogger(__name__).info(
                "benchmark_queries_completed",
                extra={"completed": query_number, "total": len(queries)},
            )
    metrics = {
        key: float(np.mean([row["metrics"][key] for row in rows])) for key in rows[0]["metrics"]
    }
    # Never silently skip images that changed or became corrupt after the frozen audit.
    result = {
        "evaluation_version": config["evaluation_version"],
        "model": encoder.model_name,
        "encoder": encoder.identity.to_dict(),
        "dataset": config["dataset"],
        "dataset_fingerprint": audit["retained_sha256"],
        "audit_sha256": content_hash(audit),
        "split_sha256": split["split_sha256"],
        "protocol_sha256": split["protocol_sha256"],
        "split_provenance": split["provenance"],
        "statistics": split["statistics"],
        "metrics": metrics,
        "embedding_dimension": encoder.embedding_dimension,
        "indexed_vectors": index.count,
        "model_loading_ms": encoder.load_time_ms,
        "total_embedding_ms": embedded.total_ms + sum(query_times),
        "gallery_embedding_ms": embedded.total_ms,
        "gallery_batch_amortized_image_latency": latency_summary(embedded.batch_amortized_image_ms),
        "query_embedding_latency": latency_summary(query_times),
        "vector_search_latency": latency_summary(search_times),
        "end_to_end_latency": latency_summary(e2e_times),
        "timing_notes": "Warm query: validation, decode, preprocessing, transfer, inference; "
        "search: full exact ranking; e2e includes MAX aggregation, excludes HTTP. "
        "Gallery per-image samples are batch-amortized, not serial observations. "
        "Model loading may include downloads; warmup excluded from embedding totals.",
        "runtime": runtime_metadata(encoder, config["runtime"]["seed"]),
    }
    output.mkdir(parents=True, exist_ok=True)
    index.save(output / "gallery-index.npz")
    write_json(output / "results.json", result)
    write_json(output / "per_query.json", rows)
    write_json(output / "failures.json", failures)
    write_json(output / "audit.json", audit)
    write_json(output / "split.json", split)
    write_json(output / "protocol.json", config)
    report = [
        f"# {encoder.model_name} — EVAL-VISUAL-V1",
        "",
        f"Split: `{split['split_sha256']}` ({split['provenance']}).",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    report += [f"| {key} | {value:.6f} |" for key, value in metrics.items()]
    report += [
        "",
        f"Indexed vectors: {index.count}; dimension: {encoder.embedding_dimension}.",
        f"Device: {encoder.device}.",
        "",
        result["timing_notes"],
        "",
        "See results.json for latency distributions and reproducibility metadata.",
        f"Failures/weak queries for manual review: {len(failures)}. "
        "Categories remain empty until supported by visual inspection.",
    ]
    (output / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    logging.getLogger(__name__).info(
        "benchmark_completed", extra={"model": encoder.model_name, "metrics": metrics}
    )
    return result


def benchmark(config_file: Path, settings: Settings, output: Path) -> dict[str, Any]:
    config = load_protocol(config_file)
    audit = audit_protocol(config, config_file)
    split = read_json(config_path(config_file, config["split"]["artifact"]))
    verify_split(split, audit, config)
    seed_runtime(config["runtime"]["seed"])
    encoder = create_encoder(settings)
    return evaluate(encoder, config, config_file, audit, split, output)
