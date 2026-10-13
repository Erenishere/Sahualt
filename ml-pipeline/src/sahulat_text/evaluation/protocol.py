from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from sahulat_text.documents.artifacts import atomic_write
from sahulat_text.documents.corpus import verify_registered_corpus
from sahulat_text.documents.serialization import canonical_json_bytes, sha256

DEFAULT_CONFIG = Path("configs/eval_text_v1.yaml")
DEFAULT_LOCK = Path("configs/eval_text_v1.protocol.json")


class TextEvaluationError(ValueError):
    """Evaluation inputs violate the pre-registered protocol; never silently repair labels."""


@dataclass(frozen=True, slots=True)
class TextEvaluationProtocol:
    version: str
    corpus_id: str
    corpus_sha256: str
    product_ids: frozenset[str]
    _settings: dict[str, Any] = field(repr=False)

    @property
    def settings(self) -> dict[str, Any]:
        return copy.deepcopy(self._settings)

    def semantic_record(self) -> dict[str, Any]:
        record = self.settings
        record["corpus"].pop("registry", None)
        return record

    @property
    def checksum(self) -> str:
        return sha256(canonical_json_bytes(self.semantic_record()))


def _positive_integer(value: Any, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise TextEvaluationError(f"{name} must be a positive integer")


def load_text_protocol(
    config_path: Path = DEFAULT_CONFIG, *, repository_root: Path = Path(".")
) -> TextEvaluationProtocol:
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("protocol_status") != "FROZEN":
        raise TextEvaluationError("protocol must be a frozen configuration object")
    version = data.get("protocol_version")
    if not isinstance(version, str) or not version:
        raise TextEvaluationError("protocol_version is required")
    queries, judgments = data["queries"], data["judgments"]
    for name in ("min_total", "min_class_per_split", "max_characters"):
        _positive_integer(queries[name], name)
    if set(queries["min_per_split"]) != {"dev", "test"}:
        raise TextEvaluationError("only dev/test query splits are supported")
    for value in queries["min_per_split"].values():
        _positive_integer(value, "min_per_split")
    if set(queries["min_intent_groups_per_split"]) != {"dev", "test"}:
        raise TextEvaluationError("intent-group minima require dev/test splits")
    for value in queries["min_intent_groups_per_split"].values():
        _positive_integer(value, "min_intent_groups_per_split")
    for name in ("language_tags", "classes"):
        values = queries[name]
        if (
            not isinstance(values, list)
            or not values
            or any(not isinstance(value, str) or not value for value in values)
            or len(values) != len(set(values))
        ):
            raise TextEvaluationError(f"{name} must contain unique non-empty strings")
    supported_judgments = {
        "grades": [0, 1, 2],
        "binary_relevance_min_grade": 1,
        "coverage": "exhaustive",
        "judges_per_query_product": 2,
        "fixed_judge_pair_per_query": True,
        "query_author_may_judge": False,
        "adjudicator_may_be_primary_judge": False,
        "positive_rationale_required": True,
        "unjudged": "error-never-implicit-zero",
        "require_answerable_query_each_split": True,
        "provenance": "human_manual",
        "disagreements": "third-human-adjudicator-required",
        "query_author_may_adjudicate": True,
        "zero_relevance": "retain-and-report-separately",
    }
    if any(
        type(judgments.get(key)) is not type(value) or judgments.get(key) != value
        for key, value in supported_judgments.items()
    ) or any(type(grade) is not int for grade in judgments["grades"]):
        raise TextEvaluationError("unsupported human-judgment policy")
    reference = data["corpus"]["registry"]
    if (
        not isinstance(reference, str)
        or Path(reference).is_absolute()
        or ":" in reference
        or "\\" in reference
    ):
        raise TextEvaluationError("corpus registry must be a portable relative reference")
    registry_path = config_path.parent / reference
    if not registry_path.resolve().is_relative_to(repository_root.resolve()):
        raise TextEvaluationError("corpus registry escapes the repository")
    registry = verify_registered_corpus(registry_path, repository_root=repository_root)
    expected = data["corpus"]
    if (
        registry["corpus_id"] != expected["id"]
        or registry["artifact_sha256"] != expected["sha256"]
        or registry["record_count"] != expected["record_count"]
    ):
        raise TextEvaluationError("protocol corpus identity/count/checksum mismatch")
    records = (repository_root / registry["artifact_path"]).read_bytes().splitlines()
    product_ids = frozenset(json.loads(record)["product_id"] for record in records)
    return TextEvaluationProtocol(
        version,
        registry["corpus_id"],
        registry["artifact_sha256"],
        product_ids,
        copy.deepcopy(data),
    )


def write_immutable_files(files: list[tuple[Path, bytes]]) -> None:
    for path, content in files:
        if path.exists() and path.read_bytes() != content:
            raise TextEvaluationError("frozen evaluation artifact drift; use a new version")
    for path, content in files:
        if not path.exists():
            atomic_write(path, content)


def preregister_protocol(
    protocol: TextEvaluationProtocol, lock_path: Path = DEFAULT_LOCK
) -> dict[str, Any]:
    lock = {
        "lock_version": "text-eval-protocol-lock-v1",
        "protocol_version": protocol.version,
        "protocol_status": "FROZEN",
        "protocol_sha256": protocol.checksum,
        "policy": protocol.semantic_record(),
    }
    write_immutable_files([(lock_path, canonical_json_bytes(lock) + b"\n")])
    return lock


def verify_protocol_lock(protocol: TextEvaluationProtocol, lock_path: Path = DEFAULT_LOCK) -> None:
    expected = {
        "lock_version": "text-eval-protocol-lock-v1",
        "protocol_version": protocol.version,
        "protocol_status": "FROZEN",
        "protocol_sha256": protocol.checksum,
        "policy": protocol.semantic_record(),
    }
    if lock_path.read_bytes() != canonical_json_bytes(expected) + b"\n":
        raise TextEvaluationError("pre-registered protocol drift; use a new version")
