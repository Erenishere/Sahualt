from pathlib import Path

import numpy as np
import pytest

from sahulat_visual.dataset import audit_dataset, make_split, records_from_audit
from sahulat_visual.errors import DatasetError, InvalidImageError
from sahulat_visual.evaluation.protocol import load_protocol
from sahulat_visual.evaluation.runner import evaluate
from sahulat_visual.index import InMemoryVectorIndex
from sahulat_visual.pipeline import embed_catalogue
from sahulat_visual.retrieval import VisualRetrievalService

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("workers", [0, 2])
def test_image_to_index_to_unique_products(encoder, image_file, tmp_path, workers):
    rows = []
    for name, product, color in [
        ("r1", "red", (255, 0, 0)),
        ("r2", "red", (240, 1, 1)),
        ("g1", "green", (0, 255, 0)),
    ]:
        image_file(f"{name}.png", color)
        rows.append({"image_id": name, "product_id": product, "image_path": f"{name}.png"})
    records = records_from_audit(audit_dataset(rows, tmp_path))
    run = embed_catalogue(encoder, records, tmp_path, batch_size=2, num_workers=workers)
    np.testing.assert_allclose(np.linalg.norm(run.vectors, axis=1), 1)
    index = InMemoryVectorIndex(encoder.identity, run.vectors, records)
    index.save(tmp_path / "catalogue.npz")
    service = VisualRetrievalService(
        encoder, InMemoryVectorIndex.load(tmp_path / "catalogue.npz"), 1
    )
    results = service.search(tmp_path / "r1.png", top_k=5)
    assert [p.product_id for p in results] == ["red", "green"]


def test_evaluator_emits_real_computed_fixture_metrics(encoder, image_file, tmp_path):
    config = load_protocol(Path("configs/eval_visual_v1.yaml"))
    config["dataset"]["root"] = str(tmp_path)
    rows = []
    for i, color in enumerate([(255, 0, 0), (245, 2, 0), (0, 255, 0), (0, 245, 2)]):
        image_file(f"{i}.png", color)
        rows.append({"image_id": str(i), "product_id": str(i // 2), "image_path": f"{i}.png"})
    audit = audit_dataset(rows, tmp_path)
    split = make_split(audit, config)
    result = evaluate(encoder, config, tmp_path / "config.yaml", audit, split, tmp_path / "report")
    assert result["metrics"]["precision_at_1"] == 1
    assert result["statistics"]["queries"] == 2
    assert result["indexed_vectors"] == 2
    assert result["model"] == "fixture"
    assert (tmp_path / "report/per_query.json").is_file()
    assert result["query_embedding_latency"]["p95_ms"] > 0


@pytest.mark.parametrize("workers", [0, 2])
def test_changed_or_corrupt_catalogue_fails_instead_of_skipping(
    encoder, image_file, tmp_path, workers
):
    path = image_file("a.png")
    rows = [{"image_id": "a", "product_id": "A", "image_path": "a.png"}]
    audit = audit_dataset(rows, tmp_path)
    records = records_from_audit(audit)
    expected = {r["image_id"]: r["pixel_sha256"] for r in audit["retained"]}
    image_file("a.png", (1, 2, 3))
    with pytest.raises(DatasetError, match="changed"):
        embed_catalogue(encoder, records, tmp_path, num_workers=workers, expected_hashes=expected)
    path.write_bytes(b"broken")
    with pytest.raises(InvalidImageError):
        embed_catalogue(encoder, records, tmp_path, num_workers=workers)
