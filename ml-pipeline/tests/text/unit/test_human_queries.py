from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest
import yaml

from sahulat_text.documents.serialization import canonical_json_bytes, sha256
from sahulat_text.evaluation import artifacts, cli
from sahulat_text.evaluation import queries as query_module
from sahulat_text.evaluation.artifacts import freeze_queries, load_frozen_queries
from sahulat_text.evaluation.labeling import validate_queries
from sahulat_text.evaluation.protocol import TextEvaluationError, load_text_protocol
from sahulat_text.evaluation.queries import import_queries, load_collection, query_status

from . import test_text_evaluation as evaluation_fixtures

registered_fixture = evaluation_fixtures.registered_fixture
evaluation_setup = evaluation_fixtures.evaluation_setup


def write_input(path, rows):
    path.write_bytes(b"".join(canonical_json_bytes(row) + b"\n" for row in rows))


def rehash_manifest(path, change):
    record = json.loads(path.read_bytes())
    record.update(change)
    record.pop("manifest_checksum")
    record["manifest_checksum"] = sha256(canonical_json_bytes(record))
    path.write_bytes(canonical_json_bytes(record) + b"\n")


def test_incremental_import_is_not_a_freeze_and_preserves_ids_and_raw_text(evaluation_setup):
    root, _, _, protocol = evaluation_setup
    rows = evaluation_fixtures.query_records()
    rows[0]["query_text"] = "  Café－style\u200d shirt?  "
    source, collection, output = root / "author.jsonl", root / "human_queries.jsonl", root / "eval"
    write_input(source, rows[:1])
    result = import_queries(protocol, source, collection, output)
    assert result["inserted"] == 1 and not result["coverage"]["requirements_pass"]
    assert load_collection(protocol, collection)[0].record() == rows[0]
    with pytest.raises(TextEvaluationError, match="insufficient"):
        freeze_queries(protocol, collection, output)
    assert not output.exists()
    write_input(source, rows[1:])
    result = import_queries(protocol, source, collection, output)
    assert result["query_count"] == 2 and result["coverage"]["requirements_pass"]
    assert query_status(protocol, collection, output)["query_freeze"] == "PENDING"


def test_import_is_idempotent_and_artifacts_contain_no_machine_paths(evaluation_setup):
    root, _, _, protocol = evaluation_setup
    source, collection, output = root / "source.jsonl", root / "human_queries.jsonl", root / "eval"
    write_input(source, evaluation_fixtures.query_records())
    import_queries(protocol, source, collection, output)
    paths = [collection, collection.with_suffix(".import.json")]
    before = [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths]
    result = import_queries(protocol, source, collection, output)
    assert result["inserted"] == 0 and result["unchanged"] == 2
    assert before == [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths]
    assert str(root).encode() not in paths[1].read_bytes()
    assert not collection.with_suffix(".import.lock").exists()


def test_registration_order_does_not_change_canonical_query_bytes(evaluation_setup):
    root, _, _, protocol = evaluation_setup
    source, output = root / "input.jsonl", root / "eval"
    rows = evaluation_fixtures.query_records()
    write_input(source, rows)
    import_queries(protocol, source, root / "one.jsonl", output)
    write_input(source, reversed(rows))
    import_queries(protocol, source, root / "two.jsonl", output)
    assert (root / "one.jsonl").read_bytes() == (root / "two.jsonl").read_bytes()


def test_conflicting_import_does_not_change_collection(evaluation_setup):
    root, _, _, protocol = evaluation_setup
    source, collection, output = root / "input.jsonl", root / "human_queries.jsonl", root / "eval"
    rows = evaluation_fixtures.query_records()
    write_input(source, rows)
    import_queries(protocol, source, collection, output)
    before = collection.read_bytes()
    rows[0]["query_text"] = "Changed TEST ONLY semantic intent"
    write_input(source, rows)
    with pytest.raises(TextEvaluationError, match="conflicting query ID"):
        import_queries(protocol, source, collection, output)
    assert collection.read_bytes() == before


def test_duplicate_rows_in_one_submission_are_rejected_even_when_identical(evaluation_setup):
    root, _, _, protocol = evaluation_setup
    source, collection = root / "input.jsonl", root / "human_queries.jsonl"
    row = evaluation_fixtures.query_records()[0]
    write_input(source, [row, row])
    with pytest.raises(TextEvaluationError, match="rows 1 and 2"):
        import_queries(protocol, source, collection, root / "eval")
    assert not collection.exists()


def test_normalized_duplicate_across_submissions_rejected(evaluation_setup):
    root, _, _, protocol = evaluation_setup
    source, collection, output = root / "input.jsonl", root / "human_queries.jsonl", root / "eval"
    rows = evaluation_fixtures.query_records()
    rows[0]["query_text"] = "  Ｂｌｕｅ  Shirt "
    write_input(source, rows[:1])
    import_queries(protocol, source, collection, output)
    rows[1]["query_text"] = "blue shirt"
    write_input(source, rows[1:])
    with pytest.raises(TextEvaluationError, match="normalized text"):
        import_queries(protocol, source, collection, output)


@pytest.mark.parametrize(
    "name",
    [
        "product_id",
        "rank",
        "scores",
        "fts_results",
        "bm25_score",
        "dense_results",
        "vector_similarity",
        "relevance_prediction",
        "predicted_grade",
        "image_url",
        "schema_version",
        "timestamp",
    ],
)
def test_blinding_and_exact_eight_field_schema_reject_extra_metadata(evaluation_setup, name):
    root, _, _, protocol = evaluation_setup
    rows = evaluation_fixtures.query_records()
    rows[0][name] = "PROHIBITED TEST ONLY METADATA"
    source, collection = root / "input.jsonl", root / "human_queries.jsonl"
    write_input(source, rows)
    with pytest.raises(TextEvaluationError, match=f"unsupported=.*{name}"):
        import_queries(protocol, source, collection, root / "eval")
    assert not collection.exists()


@pytest.mark.parametrize("value", ["", " ", "\u00a0", "\u3000", "\t", "\x00", "\ud800"])
def test_empty_unicode_whitespace_control_or_surrogate_text_rejected(evaluation_setup, value):
    _, _, _, protocol = evaluation_setup
    rows = evaluation_fixtures.query_records()
    rows[0]["query_text"] = value
    with pytest.raises(TextEvaluationError, match="query source row 1"):
        validate_queries(rows, protocol, require_complete=False)


@pytest.mark.parametrize(
    "change",
    [
        {"language_tag": "ur"},
        {"language_tag": "EN"},
        {"author_id": None},
        {"query_class": []},
        {"split": True},
        {"authorship": "llm"},
    ],
)
def test_invalid_language_and_malformed_metadata_fail_closed(evaluation_setup, change):
    _, _, _, protocol = evaluation_setup
    rows = evaluation_fixtures.query_records()
    rows[0].update(change)
    with pytest.raises(TextEvaluationError):
        validate_queries(rows, protocol, require_complete=False)


def test_missing_coordinator_id_is_rejected_not_generated(evaluation_setup):
    _, _, _, protocol = evaluation_setup
    rows = evaluation_fixtures.query_records()
    rows[0].pop("query_id")
    with pytest.raises(TextEvaluationError, match="missing=.*query_id"):
        validate_queries(rows, protocol, require_complete=False)


def test_exact_40_query_and_all_strata_requirement_with_test_only_policy(evaluation_setup):
    root, config, _, _ = evaluation_setup
    settings = yaml.safe_load(config.read_text(encoding="utf-8"))
    classes = [
        "title_terms",
        "attribute_focused",
        "paraphrase",
        "contrastive",
        "sparse_description",
    ]
    settings["queries"].update(
        {
            "min_total": 40,
            "min_per_split": {"dev": 20, "test": 20},
            "min_intent_groups_per_split": {"dev": 20, "test": 20},
            "classes": classes,
        }
    )
    config.write_text(yaml.safe_dump(settings), encoding="utf-8")
    protocol = load_text_protocol(config, repository_root=root)
    assert protocol.settings["benchmark_evidence"] is False
    rows = [
        {
            **evaluation_fixtures.query_records()[0],
            "query_id": f"TXT-Q-{i:04d}",
            "intent_group_id": f"TXT-I-{i:04d}",
            "query_text": f"TEST ONLY intent number {i}",
            "split": "dev" if i <= 20 else "test",
            "query_class": classes[(i - 1) % 5],
        }
        for i in range(1, 41)
    ]
    assert len(validate_queries(rows, protocol)) == 40
    with pytest.raises(TextEvaluationError, match="39/40"):
        validate_queries(rows[:-1], protocol)
    for row in rows:
        row["query_class"] = "title_terms"
    with pytest.raises(TextEvaluationError, match="query-class coverage"):
        validate_queries(rows, protocol)


@pytest.mark.parametrize(
    "change",
    [
        {"query_schema_version": "unsupported-v99"},
        {"protocol_version": "OTHER-PROTOCOL"},
        {"corpus_sha256": "0" * 64},
        {"split_counts": {}},
        {"record_checksums": {}},
        {"runtime": {}},
        {"manifest_version": "unsupported-v99"},
    ],
)
def test_tampered_or_unsupported_manifest_metadata_rejected(evaluation_setup, change):
    root, _, _, protocol = evaluation_setup
    source, output = root / "input.jsonl", root / "eval"
    write_input(source, evaluation_fixtures.query_records())
    freeze_queries(protocol, source, output)
    rehash_manifest(output / "queries.manifest.json", change)
    with pytest.raises(TextEvaluationError):
        load_frozen_queries(protocol, output)


def test_freeze_verify_roundtrip_idempotence_and_per_record_checksums(evaluation_setup):
    root, _, _, protocol = evaluation_setup
    source, output = root / "input.jsonl", root / "eval"
    rows = evaluation_fixtures.query_records()
    write_input(source, rows)
    manifest = freeze_queries(protocol, source, output)
    assert manifest["record_checksums"][rows[0]["query_id"]] == sha256(
        canonical_json_bytes(rows[0])
    )
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in output.iterdir()}
    write_input(source, reversed(rows))
    assert freeze_queries(protocol, source, output) == manifest
    assert len(load_frozen_queries(protocol, output)) == 2
    assert before == {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in output.iterdir()}


def test_query_bytes_tampered_but_rehashed_noncanonical_order_still_fails(evaluation_setup):
    root, _, _, protocol = evaluation_setup
    source, output = root / "input.jsonl", root / "eval"
    write_input(source, evaluation_fixtures.query_records())
    freeze_queries(protocol, source, output)
    payload = b"".join(reversed((output / "queries.jsonl").read_bytes().splitlines(keepends=True)))
    (output / "queries.jsonl").write_bytes(payload)
    rehash_manifest(output / "queries.manifest.json", {"queries_sha256": sha256(payload)})
    with pytest.raises(TextEvaluationError, match="serialization/order"):
        load_frozen_queries(protocol, output)


def test_manifest_raw_bytes_tampered_with_duplicate_key_rejected(evaluation_setup):
    root, _, _, protocol = evaluation_setup
    source, output = root / "input.jsonl", root / "eval"
    write_input(source, evaluation_fixtures.query_records())
    freeze_queries(protocol, source, output)
    path = output / "queries.manifest.json"
    path.write_bytes(b'{"query_count":999,' + path.read_bytes()[1:])
    with pytest.raises(TextEvaluationError):
        load_frozen_queries(protocol, output)


def test_collection_tampering_and_postfreeze_mutation_rejected(evaluation_setup):
    root, _, _, protocol = evaluation_setup
    source, collection, output = root / "input.jsonl", root / "human_queries.jsonl", root / "eval"
    rows = evaluation_fixtures.query_records()
    write_input(source, rows)
    import_queries(protocol, source, collection, output)
    rows[0]["query_text"] = "Altered TEST ONLY intent"
    write_input(collection, rows)
    with pytest.raises(TextEvaluationError, match="receipt drift"):
        load_collection(protocol, collection)
    collection.unlink()
    collection.with_suffix(".import.json").unlink()
    import_queries(protocol, source, collection, output)
    freeze_queries(protocol, collection, output)
    with pytest.raises(TextEvaluationError, match="freeze already started"):
        import_queries(protocol, source, collection, output)


def test_interrupted_freeze_and_import_lock_fail_closed(evaluation_setup):
    root, _, _, protocol = evaluation_setup
    source, collection, output = root / "input.jsonl", root / "human_queries.jsonl", root / "eval"
    write_input(source, evaluation_fixtures.query_records())
    collection.with_suffix(".import.lock").touch()
    with pytest.raises(TextEvaluationError, match="locked"):
        import_queries(protocol, source, collection, output)
    output.mkdir()
    (output / "queries.jsonl").write_bytes(b"")
    with pytest.raises(TextEvaluationError, match="incomplete query freeze"):
        query_status(protocol, collection, output)


@pytest.mark.parametrize(
    "action", ["import-queries", "validate-queries", "freeze-queries", "verify-queries"]
)
def test_query_cli_roundtrip_never_reads_judging_artifacts(evaluation_setup, monkeypatch, action):
    root, config, lock, protocol = evaluation_setup
    source, collection, output = root / "input.jsonl", root / "human_queries.jsonl", root / "eval"
    write_input(source, evaluation_fixtures.query_records())
    if action == "verify-queries":
        freeze_queries(protocol, source, output)

    def forbidden(*args, **kwargs):
        raise AssertionError("query stage must not read judging artifacts")

    monkeypatch.setattr(cli, "write_readiness", forbidden)
    monkeypatch.setattr(artifacts, "verify_frozen_labels", forbidden)
    argv = [
        "prepare_text_evaluation.py",
        action,
        "--config",
        str(config),
        "--lock",
        str(lock),
        "--repository-root",
        str(root),
        "--collection",
        str(collection),
        "--output-root",
        str(output),
        "--queries",
        str(source),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    assert cli.main() == 0
    assert not (output / "judgments.jsonl").exists()
    assert not (output / "qrels.jsonl").exists()


def test_cli_rejects_judgment_inputs_and_missing_human_source(evaluation_setup, monkeypatch):
    root, config, lock, _ = evaluation_setup
    argv = [
        "prepare_text_evaluation.py",
        "import-queries",
        "--config",
        str(config),
        "--lock",
        str(lock),
        "--repository-root",
        str(root),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    assert cli.main() == 2
    monkeypatch.setattr(sys, "argv", [*argv, "--judgments", "never-read.jsonl"])
    assert cli.main() == 2


def test_pending_status_is_not_a_zero_query_freeze(evaluation_setup):
    root, _, _, protocol = evaluation_setup
    status = query_status(protocol, root / "absent.jsonl", root / "eval")
    assert status["query_count"] == 0
    assert status["human_query_data"] == status["query_freeze"] == "PENDING"
    assert not status["coverage"]["requirements_pass"]
    assert "query_artifact_sha256" not in status


def test_query_workflow_has_no_retriever_or_model_dependencies():
    files = [Path(query_module.__file__), Path(cli.__file__)]
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = [
            node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        ]
        imported += [
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        ]
        assert not any(
            name.startswith(("torch", "transformers", "open_clip", "sahulat_visual"))
            or "retriever" in name
            for name in imported
        )


def test_pending_cli_writes_only_neutral_status_not_human_data(evaluation_setup, monkeypatch):
    root, config, lock, _ = evaluation_setup
    collection, output = root / "absent.jsonl", root / "eval"
    status = output / "text-query-v1-status.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prepare_text_evaluation.py",
            "query-status",
            "--config",
            str(config),
            "--lock",
            str(lock),
            "--repository-root",
            str(root),
            "--collection",
            str(collection),
            "--output-root",
            str(output),
            "--status-output",
            str(status),
        ],
    )
    assert cli.main() == 0
    record = json.loads(status.read_bytes())
    assert record["query_freeze"] == "PENDING" and record["query_count"] == 0
    assert "query_artifact_sha256" not in record
    assert not collection.exists()
    assert [path.name for path in output.iterdir()] == ["text-query-v1-status.json"]


def test_status_output_cannot_overwrite_canonical_input(evaluation_setup, monkeypatch):
    root, config, lock, _ = evaluation_setup
    collection = root / "human_queries.jsonl"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prepare_text_evaluation.py",
            "query-status",
            "--config",
            str(config),
            "--lock",
            str(lock),
            "--repository-root",
            str(root),
            "--collection",
            str(collection),
            "--status-output",
            str(collection),
        ],
    )
    assert cli.main() == 2 and not collection.exists()


def test_invalid_cli_output_option_has_no_import_side_effects(evaluation_setup, monkeypatch):
    root, config, lock, _ = evaluation_setup
    source, collection = root / "input.jsonl", root / "human_queries.jsonl"
    write_input(source, evaluation_fixtures.query_records())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prepare_text_evaluation.py",
            "import-queries",
            "--config",
            str(config),
            "--lock",
            str(lock),
            "--repository-root",
            str(root),
            "--queries",
            str(source),
            "--collection",
            str(collection),
            "--status-output",
            str(collection),
        ],
    )
    assert cli.main() == 2 and not collection.exists()


def test_orphan_import_receipt_is_not_treated_as_an_empty_human_collection(evaluation_setup):
    root, _, _, protocol = evaluation_setup
    source, collection = root / "input.jsonl", root / "human_queries.jsonl"
    write_input(source, evaluation_fixtures.query_records())
    import_queries(protocol, source, collection, root / "eval")
    collection.unlink()
    with pytest.raises(TextEvaluationError, match="orphan collection receipt"):
        query_status(protocol, collection, root / "eval")
    with pytest.raises(TextEvaluationError, match="orphan collection receipt"):
        import_queries(protocol, source, collection, root / "eval")
