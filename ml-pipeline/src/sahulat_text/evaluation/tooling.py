"""Freeze software evidence separately from human query/evaluation datasets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sahulat_text.documents.serialization import canonical_json_bytes, sha256

from .protocol import TextEvaluationError, TextEvaluationProtocol, write_immutable_files
from .queries import DEFAULT_INPUT, query_status

DEFAULT_TOOLING_REGISTRY = Path("configs/gates/text_query_tooling_v1.json")
SOURCE_PATHS = (
    "src/sahulat_text/evaluation/__init__.py",
    "src/sahulat_text/evaluation/artifacts.py",
    "src/sahulat_text/evaluation/cli.py",
    "src/sahulat_text/evaluation/labeling.py",
    "src/sahulat_text/evaluation/protocol.py",
    "src/sahulat_text/evaluation/queries.py",
    "src/sahulat_text/normalization.py",
    "scripts/prepare_text_evaluation.py",
    "configs/eval_text_v1.yaml",
    "configs/eval_text_v1.protocol.json",
    "configs/corpora/product_text_v1.json",
    "pyproject.toml",
    "docs/EVAL-TEXT-V1.md",
    "docs/text-labeling-v1.md",
    "docs/TEXT-QUERY-V1-WORKFLOW.md",
    "tests/text/unit/test_human_queries.py",
    "tests/text/unit/test_text_evaluation.py",
    "tests/text/unit/test_frozen_corpus.py",
    "reports/text_query_v1_validation.md",
)


def _path(root: Path, reference: str) -> Path:
    path = Path(reference)
    if (
        not reference
        or "\\" in reference
        or ":" in reference
        or path.is_absolute()
        or ".." in path.parts
        or not (root / path).resolve().is_relative_to(root.resolve())
    ):
        raise TextEvaluationError("tooling references must be repository-relative portable paths")
    return root / path


def freeze_tooling(
    protocol: TextEvaluationProtocol,
    *,
    repository_root: Path = Path("."),
    registry_path: Path = DEFAULT_TOOLING_REGISTRY,
    source_paths: tuple[str, ...] = SOURCE_PATHS,
) -> dict[str, Any]:
    state = query_status(
        protocol, repository_root / DEFAULT_INPUT, repository_root / "artifacts/eval_text_v1"
    )
    if state["query_count"] != 0 or state["query_freeze"] != "PENDING":
        raise TextEvaluationError(
            "this tooling-only freeze requires absent human data; review a new version"
        )
    if not source_paths or len(set(source_paths)) != len(source_paths):
        raise TextEvaluationError("tooling source inventory must be nonempty and unique")
    files = {
        reference: _path(repository_root, reference).read_bytes() for reference in source_paths
    }
    payload = {
        "registry_version": "text-query-tooling-freeze-v1",
        "tooling_id": "TEXT-QUERY-V1",
        "tooling_status": "FROZEN",
        "tooling_gate": "GREEN",
        "scope": "software-and-validation-evidence-only-not-a-human-dataset",
        "human_query_dataset": "PENDING",
        "human_queries_at_tooling_freeze": 0,
        "query_dataset_freeze": "NOT_POSSIBLE",
        "text_retrieval": "BLOCKED_PENDING_GENUINE_QUERIES_AND_JUDGMENTS",
        "protocol_version": protocol.version,
        "protocol_sha256": protocol.checksum,
        "corpus_id": protocol.corpus_id,
        "corpus_sha256": protocol.corpus_sha256,
        "corpus_count": len(protocol.product_ids),
        "source_files": {reference: sha256(content) for reference, content in files.items()},
        "source_hash_policy": "sha256-exact-file-bytes-preserve-snapshot-line-endings",
    }
    digest = sha256(canonical_json_bytes(payload))
    snapshot = f"artifacts/tooling/text-query-v1/{digest.removeprefix('sha256:')}"
    record = {**payload, "snapshot_sha256": digest, "snapshot_root": snapshot}
    registry = {**record, "registry_checksum": sha256(canonical_json_bytes(record))}
    write_immutable_files(
        [
            *[
                (_path(repository_root, f"{snapshot}/{reference}"), content)
                for reference, content in files.items()
            ],
            (
                _path(repository_root, f"{snapshot}/manifest.json"),
                canonical_json_bytes(payload) + b"\n",
            ),
            (registry_path, canonical_json_bytes(registry) + b"\n"),
        ]
    )
    return verify_tooling(
        protocol,
        repository_root=repository_root,
        registry_path=registry_path,
        check_working_tree=True,
    )


def verify_tooling(
    protocol: TextEvaluationProtocol,
    *,
    repository_root: Path = Path("."),
    registry_path: Path = DEFAULT_TOOLING_REGISTRY,
    check_working_tree: bool = False,
) -> dict[str, Any]:
    registry = json.loads(registry_path.read_bytes())
    if not isinstance(registry, dict) or not isinstance(registry.get("source_files"), dict):
        raise TextEvaluationError("tooling registry and source inventory must be objects")
    record = {key: value for key, value in registry.items() if key != "registry_checksum"}
    if registry_path.read_bytes() != canonical_json_bytes(registry) + b"\n" or registry[
        "registry_checksum"
    ] != sha256(canonical_json_bytes(record)):
        raise TextEvaluationError("frozen tooling registry checksum/serialization drift")
    expected = {
        "registry_version": "text-query-tooling-freeze-v1",
        "tooling_id": "TEXT-QUERY-V1",
        "tooling_status": "FROZEN",
        "tooling_gate": "GREEN",
        "human_query_dataset": "PENDING",
        "human_queries_at_tooling_freeze": 0,
        "query_dataset_freeze": "NOT_POSSIBLE",
        "text_retrieval": "BLOCKED_PENDING_GENUINE_QUERIES_AND_JUDGMENTS",
        "protocol_version": protocol.version,
        "protocol_sha256": protocol.checksum,
        "corpus_id": protocol.corpus_id,
        "corpus_sha256": protocol.corpus_sha256,
        "corpus_count": len(protocol.product_ids),
        "scope": "software-and-validation-evidence-only-not-a-human-dataset",
        "source_hash_policy": "sha256-exact-file-bytes-preserve-snapshot-line-endings",
    }
    if "query_artifact_sha256" in registry:
        raise TextEvaluationError(
            "a software freeze must not claim a human query artifact checksum"
        )
    if any(
        type(registry.get(key)) is not type(value) or registry.get(key) != value
        for key, value in expected.items()
    ):
        raise TextEvaluationError("tooling gate/corpus/protocol identity drift")
    payload = {
        key: value
        for key, value in record.items()
        if key not in {"snapshot_root", "snapshot_sha256"}
    }
    digest = sha256(canonical_json_bytes(payload))
    snapshot = f"artifacts/tooling/text-query-v1/{digest.removeprefix('sha256:')}"
    if registry["snapshot_sha256"] != digest or registry["snapshot_root"] != snapshot:
        raise TextEvaluationError("frozen tooling snapshot identity drift")
    if (
        _path(repository_root, f"{snapshot}/manifest.json").read_bytes()
        != canonical_json_bytes(payload) + b"\n"
    ):
        raise TextEvaluationError("frozen tooling manifest drift")
    if not registry["source_files"]:
        raise TextEvaluationError("empty tooling snapshot is not a software freeze")
    for reference, checksum in registry["source_files"].items():
        _path(repository_root, reference)
        if sha256(_path(repository_root, f"{snapshot}/{reference}").read_bytes()) != checksum:
            raise TextEvaluationError(f"frozen tooling source drift: {reference}")
        if (
            check_working_tree
            and sha256(_path(repository_root, reference).read_bytes()) != checksum
        ):
            raise TextEvaluationError(
                f"working-tree tooling drift: {reference}; preserve v1 and version changes"
            )
    return registry
