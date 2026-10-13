"""Human-query collection only: no generation, judgment reads or retrieval dependencies."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sahulat_text.documents.artifacts import atomic_write
from sahulat_text.documents.serialization import canonical_json_bytes, sha256

from .artifacts import _jsonl, load_frozen_queries
from .labeling import (
    QUERY_SCHEMA_VERSION,
    TextQuery,
    query_coverage,
    read_jsonl,
    read_jsonl_bytes,
    validate_queries,
)
from .protocol import TextEvaluationError, TextEvaluationProtocol

DEFAULT_INPUT = Path("data/eval_text_v1/human_queries.jsonl")


def _receipt(
    protocol: TextEvaluationProtocol, queries: tuple[TextQuery, ...], sources: list[str]
) -> dict[str, Any]:
    record = {
        "import_manifest_version": "human-query-collection-v1",
        "query_schema_version": QUERY_SCHEMA_VERSION,
        "protocol_version": protocol.version,
        "protocol_sha256": protocol.checksum,
        "corpus_id": protocol.corpus_id,
        "corpus_sha256": protocol.corpus_sha256,
        "query_count": len(queries),
        "collection_sha256": sha256(_jsonl(query.record() for query in queries)),
        "source_checksums": sorted(set(sources)),
        "record_checksums": {
            query.query_id: sha256(canonical_json_bytes(query.record())) for query in queries
        },
        "stage": "HUMAN_DECLARED_COLLECTION_NOT_FROZEN",
    }
    return {**record, "manifest_checksum": sha256(canonical_json_bytes(record))}


def load_collection(protocol: TextEvaluationProtocol, collection: Path) -> tuple[TextQuery, ...]:
    queries = validate_queries(read_jsonl(collection), protocol, require_complete=False)
    receipt_path = collection.with_suffix(".import.json")
    if receipt_path.exists():
        receipts = read_jsonl(receipt_path)
        if len(receipts) != 1:
            raise TextEvaluationError("collection receipt must contain one object")
        receipt = receipts[0]
        expected = _receipt(protocol, queries, receipt["source_checksums"])
        if receipt != expected or sha256(collection.read_bytes()) != receipt["collection_sha256"]:
            raise TextEvaluationError(
                "collection/receipt drift; restore the verified pair or review in a new version"
            )
    return queries


@contextmanager
def _collection_lock(collection: Path) -> Iterator[None]:
    collection.parent.mkdir(parents=True, exist_ok=True)
    lock = collection.with_suffix(".import.lock")
    try:
        handle = lock.open("x", encoding="utf-8")
    except FileExistsError as error:
        raise TextEvaluationError(
            "collection import locked; review interrupted/concurrent import"
        ) from error
    try:
        with handle:
            yield
    finally:
        lock.unlink()


def import_queries(
    protocol: TextEvaluationProtocol, source: Path, collection: Path, output_root: Path
) -> dict[str, Any]:
    # The coordinator supplies all eight fields, including IDs, class, intent group and split.
    source_payload = source.read_bytes()
    incoming = validate_queries(read_jsonl_bytes(source_payload), protocol, require_complete=False)
    if (output_root / "queries.jsonl").exists() or (output_root / "queries.manifest.json").exists():
        raise TextEvaluationError(
            "query freeze already started; use a new version, not collection edits"
        )
    with _collection_lock(collection):
        if not collection.exists() and collection.with_suffix(".import.json").exists():
            raise TextEvaluationError("orphan collection receipt; restore/review the verified pair")
        existing = load_collection(protocol, collection) if collection.exists() else ()
        by_id = {query.query_id: query for query in existing}
        inserted = 0
        for query in incoming:
            if query.query_id in by_id:
                if by_id[query.query_id] != query:
                    raise TextEvaluationError(
                        f"conflicting query ID {query.query_id}; no overwrite or automatic repair"
                    )
            else:
                by_id[query.query_id] = query
                inserted += 1
        merged = validate_queries(
            (query.record() for query in by_id.values()), protocol, require_complete=False
        )
        receipt_path = collection.with_suffix(".import.json")
        sources = (
            json.loads(receipt_path.read_bytes())["source_checksums"]
            if receipt_path.exists()
            else []
        )
        receipt = _receipt(protocol, merged, [*sources, sha256(source_payload)])
        files = [
            (collection, _jsonl(query.record() for query in merged)),
            (receipt_path, canonical_json_bytes(receipt) + b"\n"),
        ]
        for path, payload in files:
            if not path.exists() or path.read_bytes() != payload:
                atomic_write(path, payload)
    return {
        "inserted": inserted,
        "unchanged": len(incoming) - inserted,
        "query_count": len(merged),
        "collection_sha256": receipt["collection_sha256"],
        "coverage": query_coverage(merged, protocol),
    }


def query_status(
    protocol: TextEvaluationProtocol, collection: Path, output_root: Path
) -> dict[str, Any]:
    if not collection.exists() and collection.with_suffix(".import.json").exists():
        raise TextEvaluationError("orphan collection receipt; restore/review the verified pair")
    queries = load_collection(protocol, collection) if collection.exists() else ()
    has_artifact = (output_root / "queries.jsonl").exists()
    has_manifest = (output_root / "queries.manifest.json").exists()
    if has_artifact != has_manifest:
        raise TextEvaluationError("incomplete query freeze; restore/verify both canonical files")
    frozen = load_frozen_queries(protocol, output_root) if has_manifest else None
    if frozen is not None and queries and frozen != queries:
        raise TextEvaluationError("human input differs from frozen queries; no silent source drift")
    measured = frozen if frozen is not None else queries
    record = {
        "status_version": "human-query-gate-v1",
        "query_schema_version": QUERY_SCHEMA_VERSION,
        "protocol_version": protocol.version,
        "protocol_sha256": protocol.checksum,
        "corpus_id": protocol.corpus_id,
        "corpus_sha256": protocol.corpus_sha256,
        "corpus_product_count": len(protocol.product_ids),
        "query_count": len(measured),
        "human_query_data": "HUMAN_DECLARED_REQUIRES_COORDINATOR_SIGNOFF"
        if measured
        else "PENDING",
        "query_freeze": "VERIFIED" if frozen is not None else "PENDING",
        "coverage": query_coverage(measured, protocol),
        "human_provenance": "declaration only; software cannot prove authorship, scope or blinding",
    }
    if frozen is not None:
        record["query_artifact_sha256"] = sha256((output_root / "queries.jsonl").read_bytes())
    record["status_checksum"] = sha256(canonical_json_bytes(record))
    return record
