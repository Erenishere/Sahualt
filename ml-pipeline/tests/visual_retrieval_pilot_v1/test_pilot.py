from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from sahulat_visual import urdu_retrieval_pilot_v1 as pilot
from sahulat_visual.domain import EncoderIdentity, ImageMatch, ImageRecord
from sahulat_visual.errors import IndexCompatibilityError
from sahulat_visual.index import InMemoryVectorIndex
from sahulat_visual.io import content_hash, write_json
from sahulat_visual.retrieval import aggregate_products
from sahulat_visual.urdu_retrieval_pilot_v1 import (
    PILOT_VERSION,
    QUERY_COUNT,
    PilotBlockedError,
    annotation_template,
    index_path,
    index_sidecar_path,
    retrieval_metrics,
    sha256_file,
    translation_metrics,
    validate_queries,
    verify_artifact_integrity,
    verify_query_manifest,
)


def _approved_query_set(product_ids: set[str]) -> list[dict[str, object]]:
    entries = annotation_template()["queries"]
    for query in entries:
        query["language"] = "ur"
        query["script_profile"] = "urdu_script"
        query["urdu_query"] = "اصل اردو درخواست"
        query["english_reference"] = "Human reviewed English request"
        query["translation_review"] = {
            "status": "VERIFIED",
            "reviewer": "annotator-1",
            "reviewed_at": "2026-10-12",
        }
        query["relevant_product_ids"] = [sorted(product_ids)[0]]
        query["relevance_review"] = {
            "status": "VERIFIED",
            "reviewer": "annotator-2",
            "reviewed_at": "2026-10-12",
        }
    return entries


def _manifest(queries: list[dict[str, object]], source: dict[str, object]) -> dict[str, object]:
    canonical = {
        "pilot_version": PILOT_VERSION,
        "query_count": QUERY_COUNT,
        "source": source,
        "queries": queries,
    }
    return {**canonical, "manifest_sha256": content_hash(canonical)}


def test_annotation_template_has_30_unreviewed_slots_and_blocks_evaluation():
    template = annotation_template()
    assert len(template["queries"]) == 30
    errors = validate_queries(template["queries"], {"P-1"})
    assert errors
    assert any("human-verified" in error for error in errors)


def test_human_review_validation_rejects_unknown_or_duplicate_products():
    rows = _approved_query_set({"P-1", "P-2"})
    rows[0]["relevant_product_ids"] = ["P-1", "P-1"]
    rows[1]["relevant_product_ids"] = ["NOT-IN-GALLERY"]
    errors = validate_queries(rows, {"P-1", "P-2"})
    assert any("contains duplicates" in error for error in errors)
    assert any("outside gallery" in error for error in errors)


def test_manifest_checksum_is_deterministic_and_detects_annotation_drift():
    source = {"fixture": "fixture-test", "source_sha256": "a" * 64}
    first = _approved_query_set({"P-1"})
    second = json.loads(json.dumps(first))
    assert _manifest(first, source) == _manifest(second, source)
    frozen = _manifest(first, source)
    verify_query_manifest(frozen, first)
    second[0]["english_reference"] = "edited after freeze"
    with pytest.raises(PilotBlockedError, match="changed after freeze"):
        verify_query_manifest(frozen, second)


def test_retrieval_metrics_use_distinct_relevant_product_labels():
    metrics = retrieval_metrics(["P-1", "P-2", "P-3", "P-4", "P-5"], {"P-1", "P-2"})
    assert metrics == {"precision_at_1": 1.0, "recall_at_5": 1.0, "ndcg_at_5": 1.0}


def test_aggregation_returns_distinct_products_using_best_image():
    rows = [
        ImageMatch(ImageRecord("img-a1", "A", "a1.png"), 0.60),
        ImageMatch(ImageRecord("img-b", "B", "b.png"), 0.70),
        ImageMatch(ImageRecord("img-a2", "A", "a2.png"), 0.90),
    ]
    ranked = aggregate_products(rows, 5)
    assert [result.product_id for result in ranked] == ["A", "B"]
    assert ranked[0].score == 0.90
    assert ranked[0].matched_image_id == "img-a2"


def test_index_normalizes_and_rejects_duplicate_image_ids():
    identity = EncoderIdentity("pilot", "rev", "weights", "pre", 2, "v1")
    records = [ImageRecord("same", "P-1", "a.png"), ImageRecord("same", "P-2", "b.png")]
    with pytest.raises(IndexCompatibilityError, match="unique"):
        InMemoryVectorIndex(identity, np.array([[3, 4], [1, 1]], dtype=np.float32), records)


def test_index_artifact_checksum_drift_is_rejected(tmp_path: Path):
    artifact = index_path(tmp_path, "fashionclip")
    sidecar = index_sidecar_path(tmp_path, "fashionclip")
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"changed-index")
    write_json(sidecar, {"artifact_sha256": "0" * 64})
    with pytest.raises(PilotBlockedError, match="checksum drift"):
        verify_artifact_integrity(tmp_path)


def test_optional_translation_score_uses_surface_normalized_wer_and_cer():
    exact = translation_metrics("Black embroidered suit", "black embroidered suit")
    assert exact["exact_match"] is True
    assert exact["word_error_rate"] == 0
    assert exact["character_error_rate"] == 0
    mismatch = translation_metrics("red dress", "blue embroidered suit")
    assert mismatch["exact_match"] is False
    assert mismatch["word_error_rate"] > 0


def test_frozen_query_manifest_rejects_changed_khaadi_source():
    source = {"fixture": "khaadi-v1", "source_sha256": "a" * 64}
    queries = _approved_query_set({"P-1"})
    frozen = _manifest(queries, source)
    authority = SimpleNamespace(
        valid_product_ids=frozenset({"P-1"}),
        dataset_version="1",
        source_sha256="b" * 64,
        manifest_sha256="c" * 64,
        visual_audit_sha256="d" * 64,
        visual_retained=tuple({"image_id": "i"} for _ in range(2093)),
    )
    with pytest.raises(PilotBlockedError, match="source identity drifted"):
        verify_query_manifest(frozen, queries, authority)


def test_index_gate_rejects_unregistered_gallery_source(monkeypatch, tmp_path: Path):
    authority = SimpleNamespace(
        dataset_version="1",
        valid_product_ids=frozenset({"P-1"}),
        visual_retained=({"image_id": "img-1"},),
        source_sha256="a" * 64,
        manifest_sha256="b" * 64,
        visual_audit_sha256="c" * 64,
    )
    monkeypatch.setattr(pilot, "load_authority", lambda _root: authority)
    artifact = index_path(tmp_path, "fashionclip")
    sidecar = index_sidecar_path(tmp_path, "fashionclip")
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"untrusted-gallery-index")
    metadata = {
        "pilot_version": PILOT_VERSION,
        "source": {"fixture": "unauthorized-public-corpus"},
        "model": "fashionclip",
        "registry_sha256": "ignored-because-source-is-rejected-first",
    }
    write_json(
        sidecar,
        {
            "format_version": 1,
            "artifact_sha256": sha256_file(artifact),
            "metadata": metadata,
        },
    )
    with pytest.raises(PilotBlockedError, match="source identity drifted"):
        pilot.load_index("fashionclip", tmp_path)
