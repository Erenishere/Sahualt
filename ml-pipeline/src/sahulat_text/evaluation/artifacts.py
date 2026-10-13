from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from sahulat_text.documents.artifacts import atomic_write
from sahulat_text.documents.serialization import canonical_json_bytes, sha256
from sahulat_text.normalization import NORMALIZATION_VERSION, UNICODE_VERSION

from .labeling import (
    QUERY_SCHEMA_VERSION,
    TextQuery,
    query_coverage,
    read_jsonl,
    validate_judgments,
    validate_queries,
)
from .protocol import TextEvaluationError, TextEvaluationProtocol, write_immutable_files


def _jsonl(records: Iterable[dict[str, Any]]) -> bytes:
    return b"".join(canonical_json_bytes(record) + b"\n" for record in records)


def _manifest(protocol: TextEvaluationProtocol, fields: dict[str, Any]) -> dict[str, Any]:
    record = {
        "manifest_version": "text-eval-artifact-v1",
        "protocol_version": protocol.version,
        "protocol_sha256": protocol.checksum,
        "corpus_id": protocol.corpus_id,
        "corpus_sha256": protocol.corpus_sha256,
        **fields,
    }
    return {**record, "manifest_checksum": sha256(canonical_json_bytes(record))}


def _verify_manifest(protocol: TextEvaluationProtocol, path: Path) -> dict[str, Any]:
    record: dict[str, Any] = json.loads(path.read_bytes())
    payload = {key: value for key, value in record.items() if key != "manifest_checksum"}
    if record["manifest_checksum"] != sha256(canonical_json_bytes(payload)) or (
        record["manifest_version"] != "text-eval-artifact-v1"
        or record["protocol_version"] != protocol.version
        or record["protocol_sha256"] != protocol.checksum
        or record["corpus_id"] != protocol.corpus_id
        or record["corpus_sha256"] != protocol.corpus_sha256
    ):
        raise TextEvaluationError("frozen annotation manifest/protocol/corpus drift")
    return record


def query_manifest(
    protocol: TextEvaluationProtocol, queries: tuple[TextQuery, ...], payload: bytes
) -> dict[str, Any]:
    return _manifest(
        protocol,
        {
            "stage": "QUERIES_FROZEN_LABELS_PENDING",
            "query_schema_version": QUERY_SCHEMA_VERSION,
            "queries_sha256": sha256(payload),
            "query_count": len(queries),
            "split_counts": {
                split: sum(query.split == split for query in queries) for split in ("dev", "test")
            },
            "authorship": "human-declared; human process must be independently confirmed",
            "coverage": query_coverage(queries, protocol),
            "record_checksums": {
                query.query_id: sha256(canonical_json_bytes(query.record())) for query in queries
            },
            "serialization": "sorted-key-compact-json-utf8-lf-query-id-ascending",
            "runtime": {"python": "3.12", "unicode": UNICODE_VERSION},
            "duplicate_normalization_version": NORMALIZATION_VERSION,
        },
    )


def freeze_queries(
    protocol: TextEvaluationProtocol, source_path: Path, output_root: Path
) -> dict[str, Any]:
    queries = validate_queries(read_jsonl(source_path), protocol)
    payload = _jsonl(query.record() for query in queries)
    manifest = query_manifest(protocol, queries, payload)
    write_immutable_files(
        [
            (output_root / "queries.jsonl", payload),
            (output_root / "queries.manifest.json", canonical_json_bytes(manifest) + b"\n"),
        ]
    )
    return manifest


def load_frozen_queries(
    protocol: TextEvaluationProtocol, output_root: Path
) -> tuple[TextQuery, ...]:
    manifest = _verify_manifest(protocol, output_root / "queries.manifest.json")
    if manifest.get("query_schema_version") != QUERY_SCHEMA_VERSION:
        raise TextEvaluationError("unsupported or missing frozen query schema version")
    path = output_root / "queries.jsonl"
    if sha256(path.read_bytes()) != manifest["queries_sha256"]:
        raise TextEvaluationError("frozen query checksum drift")
    queries = validate_queries(read_jsonl(path), protocol)
    if len(queries) != manifest["query_count"]:
        raise TextEvaluationError("frozen query count mismatch")
    payload = _jsonl(query.record() for query in queries)
    if payload != path.read_bytes():
        raise TextEvaluationError("frozen queries violate deterministic serialization/order")
    expected_manifest = query_manifest(protocol, queries, payload)
    if manifest != expected_manifest or (output_root / "queries.manifest.json").read_bytes() != (
        canonical_json_bytes(expected_manifest) + b"\n"
    ):
        raise TextEvaluationError("frozen query manifest metadata/version/counts disagree")
    return queries


def freeze_labels(
    protocol: TextEvaluationProtocol,
    judgments_path: Path,
    adjudications_path: Path | None,
    output_root: Path,
) -> dict[str, Any]:
    queries = load_frozen_queries(protocol, output_root)
    labels = validate_judgments(
        queries,
        read_jsonl(judgments_path),
        read_jsonl(adjudications_path) if adjudications_path is not None else [],
        protocol,
    )
    outputs = {
        "qrels.jsonl": _jsonl(row.record() for row in labels.consensus),
        "judgments.jsonl": _jsonl(labels.judgments),
        "adjudications.jsonl": _jsonl(labels.adjudications),
    }
    manifest = _manifest(
        protocol,
        {
            "stage": "DATASET_FROZEN_RETRIEVAL_NOT_IMPLEMENTED",
            "queries_sha256": sha256((output_root / "queries.jsonl").read_bytes()),
            "file_checksums": {name: sha256(content) for name, content in outputs.items()},
            "query_count": len(queries),
            "product_count": len(protocol.product_ids),
            "judgment_count": len(labels.judgments),
            "qrel_count": len(labels.consensus),
            "disagreement_count": labels.disagreement_count,
            "adjudication_count": len(labels.adjudications),
            "author_adjudication_count": labels.author_adjudication_count,
            "zero_relevance_query_ids": list(labels.zero_relevance_query_ids),
            "label_provenance": "human_manual; agreements retained, "
            "disagreements explicitly adjudicated",
            "human_work_attestation": "declared by input authors; schema validation "
            "cannot prove authorship or relevance truth",
            "evaluation_executed": False,
        },
    )
    write_immutable_files(
        [
            *[(output_root / name, content) for name, content in outputs.items()],
            (output_root / "dataset.manifest.json", canonical_json_bytes(manifest) + b"\n"),
        ]
    )
    return manifest


def verify_frozen_labels(protocol: TextEvaluationProtocol, output_root: Path) -> dict[str, Any]:
    manifest = _verify_manifest(protocol, output_root / "dataset.manifest.json")
    queries = load_frozen_queries(protocol, output_root)
    if manifest["queries_sha256"] != sha256((output_root / "queries.jsonl").read_bytes()):
        raise TextEvaluationError("dataset query lineage drift")
    for name in ("qrels.jsonl", "judgments.jsonl", "adjudications.jsonl"):
        if sha256((output_root / name).read_bytes()) != manifest["file_checksums"][name]:
            raise TextEvaluationError("frozen judgment/qrel checksum drift")
    labels = validate_judgments(
        queries,
        read_jsonl(output_root / "judgments.jsonl"),
        read_jsonl(output_root / "adjudications.jsonl"),
        protocol,
    )
    if (output_root / "qrels.jsonl").read_bytes() != _jsonl(
        row.record() for row in labels.consensus
    ):
        raise TextEvaluationError("qrels disagree with human consensus/adjudication")
    if (
        manifest["judgment_count"] != len(labels.judgments)
        or manifest["qrel_count"] != len(labels.consensus)
        or manifest["query_count"] != len(queries)
        or manifest["product_count"] != len(protocol.product_ids)
        or manifest["adjudication_count"] != len(labels.adjudications)
        or manifest["disagreement_count"] != labels.disagreement_count
        or manifest["author_adjudication_count"] != labels.author_adjudication_count
        or manifest["zero_relevance_query_ids"] != list(labels.zero_relevance_query_ids)
        or manifest["evaluation_executed"] is not False
        or manifest["stage"] != "DATASET_FROZEN_RETRIEVAL_NOT_IMPLEMENTED"
    ):
        raise TextEvaluationError("annotation evidence counts disagree")
    return manifest


def write_readiness(
    protocol: TextEvaluationProtocol, output_root: Path, report_path: Path
) -> dict[str, Any]:
    query_count = judgment_count = None
    stage = "PENDING_HUMAN_QUERIES_AND_LABELS"
    if (output_root / "queries.manifest.json").exists():
        query_count = len(load_frozen_queries(protocol, output_root))
        stage = "QUERIES_FROZEN_LABELS_PENDING"
    dataset_ready = (output_root / "dataset.manifest.json").exists()
    if dataset_ready:
        manifest = verify_frozen_labels(protocol, output_root)
        stage = manifest["stage"]
        judgment_count = manifest["judgment_count"]
    query_policy = protocol.settings["queries"]
    minimum_queries = max(
        query_policy["min_total"],
        sum(
            max(
                minimum,
                query_policy["min_intent_groups_per_split"][split],
                len(query_policy["classes"]) * query_policy["min_class_per_split"],
            )
            for split, minimum in query_policy["min_per_split"].items()
        ),
    )
    record = {
        "readiness_version": "text-eval-readiness-v1",
        "stage": stage,
        "protocol_version": protocol.version,
        "protocol_status": "FROZEN",
        "protocol_sha256": protocol.checksum,
        "corpus_id": protocol.corpus_id,
        "corpus_sha256": protocol.corpus_sha256,
        "product_count": len(protocol.product_ids),
        "query_count": query_count,
        "judgment_count": judgment_count,
        "dataset_ready": dataset_ready,
        "evaluation_executed": False,
        "minimum_human_queries": minimum_queries,
        "minimum_independent_judge_rows": minimum_queries * len(protocol.product_ids) * 2,
        "language_scope": protocol.settings["queries"]["language_tags"],
    }
    record["evidence_checksum"] = sha256(canonical_json_bytes(record))
    atomic_write(output_root / "readiness.json", canonical_json_bytes(record) + b"\n")
    report = "\n".join(
        [
            "# EVAL-TEXT-V1 protocol readiness",
            "",
            f"Protocol: **FROZEN** (`{protocol.version}`)  ",
            f"Data stage: **{stage}**  ",
            f"Protocol checksum: `{protocol.checksum}`  ",
            f"Corpus: `{protocol.corpus_id}` / `{protocol.corpus_sha256}`",
            "",
            f"- Corpus products: {len(protocol.product_ids)}",
            f"- Frozen human queries: {query_count if query_count is not None else 'PENDING'}",
            "- Independent judge rows: "
            f"{judgment_count if judgment_count is not None else 'PENDING'}",
            f"- Minimum queries: {minimum_queries}; minimum independent judge rows: "
            f"{record['minimum_independent_judge_rows']}",
            f"- Dataset ready: {'YES' if dataset_ready else 'NO'}",
            "- Evaluation executed / metrics or benchmark claims: NO",
            "",
            "V1 is English-only, semantic text only, with dev/test intent groups disjoint. "
            "Every query/product pair needs two independent humans; unjudged is never zero. "
            "Disagreements require a third human. Labels and query text are not generated.",
            "",
            "See docs/EVAL-TEXT-V1.md and docs/text-labeling-v1.md for the pre-registered "
            "metrics, cohort/denominator rules, schemas, human workflow and limitations. "
            "PostgreSQL FTS remains pending ADR-ML-002; no retriever, Search infrastructure, "
            "embedding, database write or Visual V1 change is implemented here.",
            "",
        ]
    )
    atomic_write(report_path, report.encode("utf-8"))
    return record
