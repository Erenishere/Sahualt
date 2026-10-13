from __future__ import annotations

import copy
import json
from dataclasses import replace
from uuid import UUID

import pytest
import yaml

from sahulat_text.documents.corpus import freeze_registered_corpus
from sahulat_text.documents.serialization import canonical_json_bytes, sha256
from sahulat_text.evaluation.artifacts import (
    freeze_labels,
    freeze_queries,
    load_frozen_queries,
    verify_frozen_labels,
    write_readiness,
)
from sahulat_text.evaluation.labeling import read_jsonl, validate_judgments, validate_queries
from sahulat_text.evaluation.protocol import (
    DEFAULT_CONFIG,
    TextEvaluationError,
    load_text_protocol,
    preregister_protocol,
    verify_protocol_lock,
)

from . import test_frozen_corpus as corpus_fixtures

registered_fixture = corpus_fixtures.registered_fixture


@pytest.fixture
def evaluation_setup(registered_fixture):
    root, registry_path, registry, _ = registered_fixture
    freeze_registered_corpus(registry_path, repository_root=root)
    policy = yaml.safe_load(DEFAULT_CONFIG.read_text(encoding="utf-8"))
    policy["protocol_version"] = "SYNTHETIC-TEXT-PROTOCOL-TEST"
    policy["benchmark_evidence"] = False
    policy["corpus"] = {
        "registry": registry_path.name,
        "id": registry["corpus_id"],
        "sha256": registry["artifact_sha256"],
        "record_count": registry["record_count"],
    }
    policy["queries"].update(
        {
            "min_total": 2,
            "min_per_split": {"dev": 1, "test": 1},
            "min_intent_groups_per_split": {"dev": 1, "test": 1},
            "classes": ["title_terms"],
        }
    )
    config = root / "protocol.yaml"
    config.write_text(yaml.safe_dump(policy), encoding="utf-8")
    protocol = load_text_protocol(config, repository_root=root)
    lock = root / "protocol.lock.json"
    preregister_protocol(protocol, lock)
    return root, config, lock, protocol


def query_records():
    return [
        {
            "query_id": f"TXT-Q-{index:04d}",
            "query_text": text,
            "language_tag": "en",
            "query_class": "title_terms",
            "split": split,
            "intent_group_id": f"TXT-I-{index:04d}",
            "author_id": "author-a",
            "authorship": "human",
        }
        for index, text, split in [
            (1, "Synthetic first intent", "dev"),
            (2, "Different second intent", "test"),
        ]
    ]


def judgment_records(queries=None):
    return [
        {
            "query_id": query["query_id"],
            "product_id": str(UUID(int=1)),
            "judge_id": judge,
            "grade": 2,
            "rationale": "Synthetic test relevance explanation.",
            "provenance": "human_manual",
        }
        for query in (queries or query_records())
        for judge in ("judge-a", "judge-b")
    ]


def adjudication():
    return {
        "query_id": "TXT-Q-0001",
        "product_id": str(UUID(int=1)),
        "adjudicator_id": "reviewer-c",
        "grade": 1,
        "rationale": "Synthetic test adjudication explanation.",
        "provenance": "human_manual",
    }


def write_jsonl(path, records):
    path.write_bytes(b"".join(canonical_json_bytes(record) + b"\n" for record in records))


def test_preregistration_is_immutable_and_repeatable(evaluation_setup) -> None:
    _, _, lock, protocol = evaluation_setup
    before = (lock.read_bytes(), lock.stat().st_mtime_ns)
    preregister_protocol(protocol, lock)
    verify_protocol_lock(protocol, lock)
    assert before == (lock.read_bytes(), lock.stat().st_mtime_ns)
    assert protocol.settings["benchmark_evidence"] is False


def test_policy_changes_fail_existing_preregistration(evaluation_setup) -> None:
    root, config, lock, protocol = evaluation_setup
    policy = yaml.safe_load(config.read_text(encoding="utf-8"))
    policy["latency"]["seed"] = 99
    config.write_text(yaml.safe_dump(policy), encoding="utf-8")
    changed = load_text_protocol(config, repository_root=root)
    assert changed.checksum != protocol.checksum
    with pytest.raises(TextEvaluationError, match="drift"):
        preregister_protocol(changed, lock)
    with pytest.raises(TextEvaluationError, match="drift"):
        verify_protocol_lock(changed, lock)


def test_registry_relocation_does_not_change_semantic_protocol_hash(evaluation_setup) -> None:
    root, config, _, protocol = evaluation_setup
    policy = yaml.safe_load(config.read_text(encoding="utf-8"))
    original = root / policy["corpus"]["registry"]
    relocated = root / "relocated-registry.json"
    relocated.write_bytes(original.read_bytes())
    policy["corpus"]["registry"] = relocated.name
    config.write_text(yaml.safe_dump(policy), encoding="utf-8")
    assert load_text_protocol(config, repository_root=root).checksum == protocol.checksum
    assert "registry" not in protocol.semantic_record()["corpus"]


def test_protocol_settings_cannot_be_mutated_by_callers(evaluation_setup) -> None:
    _, _, _, protocol = evaluation_setup
    settings = protocol.settings
    settings["queries"]["min_total"] = 100
    assert protocol.settings["queries"]["min_total"] == 2


def test_protocol_refuses_wrong_corpus_checksum(evaluation_setup) -> None:
    root, config, _, _ = evaluation_setup
    policy = yaml.safe_load(config.read_text(encoding="utf-8"))
    policy["corpus"]["sha256"] = "0" * 64
    config.write_text(yaml.safe_dump(policy), encoding="utf-8")
    with pytest.raises(TextEvaluationError, match="corpus identity"):
        load_text_protocol(config, repository_root=root)


@pytest.mark.parametrize("value", [-1, 0, True, "40"])
def test_invalid_protocol_counts_rejected(evaluation_setup, value) -> None:
    root, config, _, _ = evaluation_setup
    policy = yaml.safe_load(config.read_text(encoding="utf-8"))
    policy["queries"]["min_total"] = value
    config.write_text(yaml.safe_dump(policy), encoding="utf-8")
    with pytest.raises(TextEvaluationError, match="positive integer"):
        load_text_protocol(config, repository_root=root)


def test_queries_are_human_declared_and_original_text_is_preserved(evaluation_setup) -> None:
    _, _, _, protocol = evaluation_setup
    records = query_records()
    records[0]["query_text"] = "  Café shirt?  "
    queries = validate_queries(records, protocol)
    assert queries[0].query_text == "  Café shirt?  "
    assert validate_queries(reversed(records), protocol) == queries


@pytest.mark.parametrize(
    "change",
    [
        {"language_tag": "ur"},
        {"query_class": "unknown"},
        {"split": "train"},
        {"authorship": "llm_generated"},
        {"query_text": "\t"},
        {"query_text": "x" * 513},
        {"price_max": 5000},
    ],
)
def test_invalid_or_out_of_scope_query_records_rejected(evaluation_setup, change) -> None:
    _, _, _, protocol = evaluation_setup
    records = query_records()
    records[0].update(change)
    with pytest.raises(TextEvaluationError):
        validate_queries(records, protocol)


def test_duplicate_normalized_query_and_intent_split_leakage_rejected(evaluation_setup) -> None:
    _, _, _, protocol = evaluation_setup
    records = query_records()
    records[0]["query_text"] = " Ｂｌｕｅ  Shirt "
    records[1]["query_text"] = "blue shirt"
    with pytest.raises(TextEvaluationError, match="duplicate"):
        validate_queries(records, protocol)
    records = query_records()
    records[1]["intent_group_id"] = records[0]["intent_group_id"]
    with pytest.raises(TextEvaluationError, match="leakage"):
        validate_queries(records, protocol)


def test_missing_queries_or_split_coverage_rejected(evaluation_setup) -> None:
    _, _, _, protocol = evaluation_setup
    with pytest.raises(TextEvaluationError, match="insufficient"):
        validate_queries(query_records()[:1], protocol)
    records = query_records()
    records[1]["split"] = "dev"
    with pytest.raises(TextEvaluationError, match="coverage"):
        validate_queries(records, protocol)


def test_complete_two_judge_consensus_and_row_order_are_deterministic(evaluation_setup) -> None:
    _, _, _, protocol = evaluation_setup
    queries = validate_queries(query_records(), protocol)
    first = validate_judgments(queries, judgment_records(), [], protocol)
    second = validate_judgments(queries, reversed(judgment_records()), [], protocol)
    assert first == second
    assert len(first.consensus) == 2 and len(first.judgments) == 4
    assert first.disagreement_count == 0


@pytest.mark.parametrize("grade", [None, "0", True, 1.5, -1, 3])
def test_missing_or_malformed_grades_are_not_zero(evaluation_setup, grade) -> None:
    _, _, _, protocol = evaluation_setup
    records = judgment_records()
    records[0]["grade"] = grade
    with pytest.raises(TextEvaluationError, match="grade"):
        validate_judgments(validate_queries(query_records(), protocol), records, [], protocol)


def test_missing_judge_and_duplicate_conflicting_row_rejected(evaluation_setup) -> None:
    _, _, _, protocol = evaluation_setup
    queries = validate_queries(query_records(), protocol)
    with pytest.raises(TextEvaluationError, match="unjudged"):
        validate_judgments(queries, judgment_records()[:-1], [], protocol)
    records = judgment_records()
    records.append({**records[0], "grade": 1})
    with pytest.raises(TextEvaluationError, match="duplicate"):
        validate_judgments(queries, records, [], protocol)


def test_fixed_judge_pair_per_query_is_enforced_for_multiple_products(evaluation_setup) -> None:
    _, _, _, protocol = evaluation_setup
    second_product = str(UUID(int=2))
    expanded = replace(protocol, product_ids=protocol.product_ids | {second_product})
    records = judgment_records()
    records += [{**row, "product_id": second_product} for row in judgment_records()]
    records[-1]["judge_id"] = "judge-c"
    with pytest.raises(TextEvaluationError, match="coverage"):
        validate_judgments(validate_queries(query_records(), expanded), records, [], expanded)


@pytest.mark.parametrize(
    "change",
    [
        {"query_id": "TXT-Q-9999"},
        {"product_id": "KH123"},
        {"product_id": str(UUID(int=2))},
        {"judge_id": "author-a"},
        {"provenance": "model_generated"},
        {"rationale": ""},
    ],
)
def test_invalid_judgment_identity_roles_provenance_or_evidence_rejected(
    evaluation_setup, change
) -> None:
    _, _, _, protocol = evaluation_setup
    records = judgment_records()
    records[0].update(change)
    with pytest.raises(TextEvaluationError):
        validate_judgments(validate_queries(query_records(), protocol), records, [], protocol)


def test_disagreements_require_explicit_third_human_not_averaging(evaluation_setup) -> None:
    _, _, _, protocol = evaluation_setup
    queries = validate_queries(query_records(), protocol)
    records = judgment_records()
    records[0]["grade"] = 1
    with pytest.raises(TextEvaluationError, match="unresolved"):
        validate_judgments(queries, records, [], protocol)
    resolved = validate_judgments(queries, records, [adjudication()], protocol)
    assert resolved.disagreement_count == 1 and resolved.consensus[0].grade == 1
    assert len(resolved.adjudications) == 1


def test_adjudicator_cannot_be_primary_judge_or_overwrite_agreement(evaluation_setup) -> None:
    _, _, _, protocol = evaluation_setup
    queries = validate_queries(query_records(), protocol)
    records = judgment_records()
    with pytest.raises(TextEvaluationError, match="agreed"):
        validate_judgments(queries, records, [adjudication()], protocol)
    records[0]["grade"] = 1
    with pytest.raises(TextEvaluationError, match="third"):
        validate_judgments(
            queries, records, [{**adjudication(), "adjudicator_id": "judge-a"}], protocol
        )
    disclosed = validate_judgments(
        queries, records, [{**adjudication(), "adjudicator_id": "author-a"}], protocol
    )
    assert disclosed.author_adjudication_count == 1


def test_zero_relevance_queries_retained_but_each_split_needs_answerable_query(
    evaluation_setup,
) -> None:
    _, _, _, protocol = evaluation_setup
    records = query_records()
    records += [
        {
            **record,
            "query_id": f"TXT-Q-{index:04d}",
            "query_text": f"Unanswerable synthetic intent {index}",
            "intent_group_id": f"TXT-I-{index:04d}",
        }
        for index, record in enumerate(copy.deepcopy(records), start=3)
    ]
    queries = validate_queries(records, protocol)
    labels = judgment_records(records)
    for row in labels:
        if row["query_id"] in {"TXT-Q-0003", "TXT-Q-0004"}:
            row.update({"grade": 0, "rationale": ""})
    result = validate_judgments(queries, labels, [], protocol)
    assert result.zero_relevance_query_ids == ("TXT-Q-0003", "TXT-Q-0004")
    assert len(result.consensus) == 4
    for row in labels:
        row.update({"grade": 0, "rationale": ""})
    with pytest.raises(TextEvaluationError, match="answerable"):
        validate_judgments(queries, labels, [], protocol)


@pytest.mark.parametrize(
    "payload",
    [b"\xff", b"{bad json}\n", b"[]\n", b"\n", b'{"grade":0,"grade":2}\n', b'{"grade":NaN}\n'],
)
def test_malformed_jsonl_is_explicit_failure(tmp_path, payload) -> None:
    path = tmp_path / "invalid.jsonl"
    path.write_bytes(payload)
    with pytest.raises(TextEvaluationError):
        read_jsonl(path)


def test_query_and_label_artifact_freezing_is_idempotent_and_verified(evaluation_setup) -> None:
    root, _, _, protocol = evaluation_setup
    queries_path, judgments_path = root / "human-queries.jsonl", root / "human-judgments.jsonl"
    write_jsonl(queries_path, query_records())
    write_jsonl(judgments_path, judgment_records())
    output = root / "eval"
    freeze_queries(protocol, queries_path, output)
    manifest = freeze_labels(protocol, judgments_path, None, output)
    assert manifest["query_count"] == 2 and manifest["judgment_count"] == 4
    assert manifest["qrel_count"] == 2 and not manifest["evaluation_executed"]
    before = {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in output.iterdir()}
    write_jsonl(queries_path, reversed(query_records()))
    write_jsonl(judgments_path, reversed(judgment_records()))
    freeze_queries(protocol, queries_path, output)
    freeze_labels(protocol, judgments_path, None, output)
    assert before == {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in output.iterdir()
    }
    assert verify_frozen_labels(protocol, output) == manifest
    assert (
        sha256((output / "qrels.jsonl").read_bytes()) == manifest["file_checksums"]["qrels.jsonl"]
    )


def test_missing_labels_never_create_partial_qrels(evaluation_setup) -> None:
    root, _, _, protocol = evaluation_setup
    queries_path, judgments_path = root / "queries-input.jsonl", root / "labels-input.jsonl"
    write_jsonl(queries_path, query_records())
    write_jsonl(judgments_path, judgment_records()[:-1])
    output = root / "eval"
    freeze_queries(protocol, queries_path, output)
    with pytest.raises(TextEvaluationError):
        freeze_labels(protocol, judgments_path, None, output)
    assert not (output / "qrels.jsonl").exists()
    assert not (output / "dataset.manifest.json").exists()


def test_frozen_query_drift_detected_and_not_replaced(evaluation_setup) -> None:
    root, _, _, protocol = evaluation_setup
    source, output = root / "queries-input.jsonl", root / "eval"
    write_jsonl(source, query_records())
    freeze_queries(protocol, source, output)
    (output / "queries.jsonl").write_bytes(b"tampered\n")
    with pytest.raises(TextEvaluationError, match="checksum drift"):
        load_frozen_queries(protocol, output)
    with pytest.raises(TextEvaluationError, match="artifact drift"):
        freeze_queries(protocol, source, output)


def test_readiness_without_human_data_is_pending_not_empty_benchmark(evaluation_setup) -> None:
    root, _, _, protocol = evaluation_setup
    record = write_readiness(protocol, root / "eval", root / "report.md")
    assert record["stage"] == "PENDING_HUMAN_QUERIES_AND_LABELS"
    assert record["query_count"] is None and record["judgment_count"] is None
    assert record["minimum_independent_judge_rows"] == 4
    assert not record["dataset_ready"] and not record["evaluation_executed"]
    assert not (root / "eval" / "queries.jsonl").exists()
    assert not (root / "eval" / "qrels.jsonl").exists()
    assert json.loads((root / "eval" / "readiness.json").read_bytes()) == record


def test_intent_group_minimum_cannot_be_replaced_by_paraphrase_count(evaluation_setup) -> None:
    _, config, _, _ = evaluation_setup
    settings = yaml.safe_load(config.read_text(encoding="utf-8"))
    settings["queries"]["min_intent_groups_per_split"]["dev"] = 2
    config.write_text(yaml.safe_dump(settings), encoding="utf-8")
    protocol = load_text_protocol(config, repository_root=config.parent)
    with pytest.raises(TextEvaluationError, match="intent-group coverage"):
        validate_queries(query_records(), protocol)


def test_duplicate_query_objects_not_silently_collapsed_during_label_validation(
    evaluation_setup,
) -> None:
    _, _, _, protocol = evaluation_setup
    queries = validate_queries(query_records(), protocol)
    with pytest.raises(TextEvaluationError, match="duplicate query"):
        validate_judgments((*queries, queries[0]), judgment_records(), [], protocol)


def test_rehashed_manifest_statistics_are_checked_against_source_labels(evaluation_setup) -> None:
    root, _, _, protocol = evaluation_setup
    queries_path, judgments_path = root / "human-queries.jsonl", root / "human-judgments.jsonl"
    write_jsonl(queries_path, query_records())
    write_jsonl(judgments_path, judgment_records())
    output = root / "eval"
    freeze_queries(protocol, queries_path, output)
    manifest = freeze_labels(protocol, judgments_path, None, output)
    manifest["disagreement_count"] = 999
    manifest.pop("manifest_checksum")
    manifest["manifest_checksum"] = sha256(canonical_json_bytes(manifest))
    (output / "dataset.manifest.json").write_bytes(canonical_json_bytes(manifest) + b"\n")
    with pytest.raises(TextEvaluationError, match="counts disagree"):
        verify_frozen_labels(protocol, output)
