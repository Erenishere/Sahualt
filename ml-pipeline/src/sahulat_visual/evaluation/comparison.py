from pathlib import Path
from typing import Any

import numpy as np

from ..errors import DatasetError
from ..io import read_json, write_json


def paired_intervals(
    a: list[dict[str, Any]], b: list[dict[str, Any]], seed: int = 42, replicates: int = 2000
) -> dict[str, Any]:
    """Bootstrap products, preserving all views within a resampled product cluster."""
    by_id = {row["query"]["image_id"]: row for row in b}
    if (
        len(by_id) != len(b)
        or len(a) != len(b)
        or {row["query"]["image_id"] for row in a} != set(by_id)
    ):
        raise DatasetError("Per-query results are not paired")
    products = sorted({row["query"]["product_id"] for row in a})
    if not products:
        raise DatasetError("No paired queries for uncertainty analysis")
    positions = {product: i for i, product in enumerate(products)}
    counts = np.zeros(len(products))
    keys = ["precision_at_1", "map_at_5"]
    sums = np.zeros((len(products), len(keys)))
    for row in a:
        other = by_id[row["query"]["image_id"]]
        if row["query"] != other["query"]:
            raise DatasetError("Per-query ground truth differs between candidates")
        position = positions[row["query"]["product_id"]]
        counts[position] += 1
        sums[position] += [other["metrics"][key] - row["metrics"][key] for key in keys]
    rng = np.random.default_rng(seed)
    samples = rng.integers(0, len(products), size=(replicates, len(products)))
    deltas = sums[samples].sum(axis=1) / counts[samples].sum(axis=1)[:, None]
    return {
        "method": "paired-product-cluster-percentile-bootstrap",
        "seed": seed,
        "replicates": replicates,
        "direction": "fashionclip-minus-openclip",
        "metrics": {
            key: {
                "delta": float(sums[:, i].sum() / counts.sum()),
                "ci95_low": float(np.percentile(deltas[:, i], 2.5)),
                "ci95_high": float(np.percentile(deltas[:, i], 97.5)),
            }
            for i, key in enumerate(keys)
        },
    }


def compare(openclip_file: Path, fashionclip_file: Path, output: Path) -> None:
    a, b = read_json(openclip_file), read_json(fashionclip_file)
    if a["model"] != "openclip" or b["model"] != "fashionclip":
        raise DatasetError("Comparison requires OpenCLIP and FashionCLIP in that order")
    for key in (
        "evaluation_version",
        "dataset_fingerprint",
        "audit_sha256",
        "split_sha256",
        "protocol_sha256",
        "statistics",
        "indexed_vectors",
    ):
        if a[key] != b[key]:
            raise DatasetError(f"Incomparable benchmark results: {key} differs")
    timing_comparable = all(
        a["runtime"].get(key) == b["runtime"].get(key)
        for key in ("platform", "processor", "device", "gpu", "torch_threads")
    )
    rows: list[tuple[str, Any, Any, bool | None]] = [
        (key, a["metrics"][key], b["metrics"][key], True) for key in a["metrics"]
    ]
    rows += [
        (
            "Query embedding latency (mean ms)",
            a["query_embedding_latency"]["mean_ms"],
            b["query_embedding_latency"]["mean_ms"],
            False if timing_comparable else None,
        ),
        (
            "Search latency (mean ms)",
            a["vector_search_latency"]["mean_ms"],
            b["vector_search_latency"]["mean_ms"],
            False if timing_comparable else None,
        ),
        ("Embedding dimension", a["embedding_dimension"], b["embedding_dimension"], None),
    ]
    lines = [
        "# Visual model comparison",
        "",
        "Actual EVAL-VISUAL-V1 measurements.",
        "",
        f"Frozen split: `{a['split_sha256']}`.",
        "",
        "| Metric | OpenCLIP | FashionCLIP | Numerical winner |",
        "| --- | ---: | ---: | --- |",
    ]
    for name, av, bv, higher in rows:
        winner = (
            "—"
            if higher is None
            else "Tie"
            if av == bv
            else ("OpenCLIP" if (av > bv) == higher else "FashionCLIP")
        )
        lines.append(f"| {name} | {av:.6f} | {bv:.6f} | {winner} |")
    lines += [
        "",
        "Numerical winners are descriptive, not significance claims. No automatic "
        "production selection is made. Review per-query failures, practical effect sizes, "
        "latency distributions, memory and out-of-domain catalogue evidence in ADR-ML-001.",
        "",
        f"Same recorded timing environment: {timing_comparable}. "
        "Background system load and cache state still affect timings.",
        "",
        "Both candidates use ViT-B/32. OpenCLIP uses its native implementation; "
        "FashionCLIP uses the Transformers vision projection. Each uses checkpoint-specific "
        "preprocessing. Khaadi same-product quality does not establish general commerce "
        "or user-photo performance. Model loading includes cache/download effects; compare "
        "warm inference separately.",
    ]
    paired_a, paired_b = (
        openclip_file.with_name("per_query.json"),
        fashionclip_file.with_name("per_query.json"),
    )
    uncertainty = None
    if paired_a.exists() and paired_b.exists():
        uncertainty = paired_intervals(read_json(paired_a), read_json(paired_b))
        lines += [
            "",
            "Paired product-cluster bootstrap, 2,000 resamples, seed 42. "
            "Differences below are FashionCLIP minus OpenCLIP; intervals describe "
            "sampling uncertainty within this dataset, not catalogue generalization.",
            "",
        ]
        for key, values in uncertainty["metrics"].items():
            lines.append(
                f"* {key}: delta {values['delta']:.6f}, "
                f"95% interval [{values['ci95_low']:.6f}, {values['ci95_high']:.6f}]."
            )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_json(
        output.with_suffix(".json"),
        {
            "openclip": a,
            "fashionclip": b,
            "paired_uncertainty": uncertainty,
            "timing_comparable": timing_comparable,
            "production_decision": "requires-ADR-review",
        },
    )
