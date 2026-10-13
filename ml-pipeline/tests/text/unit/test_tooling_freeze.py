from __future__ import annotations

import json

import pytest

from sahulat_text.documents.serialization import canonical_json_bytes, sha256
from sahulat_text.evaluation.protocol import TextEvaluationError
from sahulat_text.evaluation.tooling import freeze_tooling, verify_tooling

from . import test_text_evaluation as evaluation_fixtures

registered_fixture = evaluation_fixtures.registered_fixture
evaluation_setup = evaluation_fixtures.evaluation_setup


@pytest.fixture
def tooling_setup(evaluation_setup):
    root, _, _, protocol = evaluation_setup
    (root / "src").mkdir()
    (root / "src/fixture.py").write_bytes(b"# SYNTHETIC SOFTWARE SNAPSHOT TEST ONLY\r\n")
    registry = root / "tooling.json"
    freeze_tooling(
        protocol, repository_root=root, registry_path=registry, source_paths=("src/fixture.py",)
    )
    return root, registry, protocol


def test_tooling_freeze_is_not_a_query_dataset_and_is_idempotent(tooling_setup):
    root, registry, protocol = tooling_setup
    record = verify_tooling(protocol, repository_root=root, registry_path=registry)
    assert record["human_query_dataset"] == "PENDING"
    assert record["human_queries_at_tooling_freeze"] == 0
    assert record["query_dataset_freeze"] == "NOT_POSSIBLE"
    assert "query_artifact_sha256" not in record
    assert record["text_retrieval"].startswith("BLOCKED")
    assert not (root / "artifacts/eval_text_v1/queries.jsonl").exists()
    assert not (root / "data/eval_text_v1/human_queries.jsonl").exists()
    snapshot = root / record["snapshot_root"]
    before = [(p, p.read_bytes(), p.stat().st_mtime_ns) for p in snapshot.rglob("*") if p.is_file()]
    registry_before = registry.read_bytes(), registry.stat().st_mtime_ns
    freeze_tooling(
        protocol, repository_root=root, registry_path=registry, source_paths=("src/fixture.py",)
    )
    assert registry_before == (registry.read_bytes(), registry.stat().st_mtime_ns)
    assert before == [
        (p, p.read_bytes(), p.stat().st_mtime_ns) for p in snapshot.rglob("*") if p.is_file()
    ]
    assert str(root).encode() not in registry.read_bytes()


def test_workspace_changes_do_not_destroy_saved_release_but_refreeze_refuses(tooling_setup):
    root, registry, protocol = tooling_setup
    (root / "src/fixture.py").write_bytes(b"# changed software\n")
    verify_tooling(protocol, repository_root=root, registry_path=registry)
    with pytest.raises(TextEvaluationError, match="working-tree tooling drift"):
        verify_tooling(
            protocol, repository_root=root, registry_path=registry, check_working_tree=True
        )
    with pytest.raises(TextEvaluationError, match="frozen evaluation artifact drift"):
        freeze_tooling(
            protocol, repository_root=root, registry_path=registry, source_paths=("src/fixture.py",)
        )


def test_saved_snapshot_tampering_is_detected_not_repaired(tooling_setup):
    root, registry, protocol = tooling_setup
    record = json.loads(registry.read_bytes())
    (root / record["snapshot_root"] / "src/fixture.py").write_bytes(b"tampered")
    with pytest.raises(TextEvaluationError, match="source drift"):
        verify_tooling(protocol, repository_root=root, registry_path=registry)


@pytest.mark.parametrize(
    "change",
    [
        {"tooling_status": "GREEN"},
        {"human_query_dataset": "GREEN"},
        {"human_queries_at_tooling_freeze": False},
        {"query_dataset_freeze": "FROZEN"},
        {"corpus_sha256": "0" * 64},
        {"protocol_version": "OTHER"},
        {"snapshot_root": "../escape"},
        {"source_files": {}},
    ],
)
def test_even_rehashed_registry_drift_is_detected(tooling_setup, change):
    root, registry, protocol = tooling_setup
    record = json.loads(registry.read_bytes())
    record.update(change)
    record.pop("registry_checksum")
    record["registry_checksum"] = sha256(canonical_json_bytes(record))
    registry.write_bytes(canonical_json_bytes(record) + b"\n")
    with pytest.raises(TextEvaluationError):
        verify_tooling(protocol, repository_root=root, registry_path=registry)


def test_query_presence_prevents_zero_query_bootstrap_freeze(evaluation_setup):
    root, _, _, protocol = evaluation_setup
    collection = root / "data/eval_text_v1/human_queries.jsonl"
    collection.parent.mkdir(parents=True)
    collection.write_bytes(canonical_json_bytes(evaluation_fixtures.query_records()[0]) + b"\n")
    with pytest.raises(TextEvaluationError, match="absent human data"):
        freeze_tooling(
            protocol,
            repository_root=root,
            registry_path=root / "gate.json",
            source_paths=("not-read.py",),
        )


@pytest.mark.parametrize("reference", ["../outside.py", "C:/outside.py", "src\\local.py"])
def test_tooling_source_path_escape_rejected(evaluation_setup, reference):
    root, _, _, protocol = evaluation_setup
    with pytest.raises(TextEvaluationError, match="portable paths"):
        freeze_tooling(
            protocol,
            repository_root=root,
            registry_path=root / "gate.json",
            source_paths=(reference,),
        )
