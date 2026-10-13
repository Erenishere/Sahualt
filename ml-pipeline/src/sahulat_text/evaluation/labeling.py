from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from sahulat_text.normalization import normalize_text

from .protocol import TextEvaluationError, TextEvaluationProtocol

QUERY_SCHEMA_VERSION = "text-query-input-v1"
QUERY_FIELDS = {
    "query_id",
    "query_text",
    "language_tag",
    "query_class",
    "split",
    "intent_group_id",
    "author_id",
    "authorship",
}


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    record: dict[str, Any] = {}
    for key, value in pairs:
        if key in record:
            raise TextEvaluationError("duplicate JSON key; no silent winner")
        record[key] = value
    return record


def _invalid_constant(value: str) -> None:
    raise TextEvaluationError("nonfinite JSON numbers are forbidden")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return read_jsonl_bytes(path.read_bytes())


def read_jsonl_bytes(payload: bytes) -> list[dict[str, Any]]:
    lines = payload.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    records = []
    for position, line in enumerate(lines, start=1):
        try:
            record = json.loads(
                line.decode("utf-8", errors="strict"),
                object_pairs_hook=_unique_object,
                parse_constant=_invalid_constant,
            )
        except (UnicodeDecodeError, ValueError) as error:
            raise TextEvaluationError(f"invalid JSONL at source row {position}: {error}") from error
        if not isinstance(record, dict):
            raise TextEvaluationError(f"JSONL row {position} must be an object")
        records.append(record)
    return records


def _fields(record: Mapping[str, Any], expected: set[str]) -> None:
    if set(record) != expected:
        missing, extra = sorted(expected - set(record)), sorted(set(record) - expected)
        raise TextEvaluationError(
            f"missing or unsupported annotation fields: missing={missing}, unsupported={extra}"
        )


def _text(record: Mapping[str, Any], name: str, *, allow_empty: bool = False) -> str:
    value = record[name]
    if (
        not isinstance(value, str)
        or (not allow_empty and not value.strip())
        or any(unicodedata.category(character) == "Cc" for character in value)
        or any(unicodedata.category(character) == "Cs" for character in value)
    ):
        raise TextEvaluationError(f"invalid {name}")
    return value


def _identifier(record: Mapping[str, Any], name: str) -> str:
    value = _text(record, name)
    if not re.fullmatch(r"[a-z][a-z0-9_-]{1,63}", value):
        raise TextEvaluationError(f"{name} must be an opaque reviewer alias, not PII")
    return value


def _grade(record: Mapping[str, Any]) -> int:
    value = record["grade"]
    if isinstance(value, bool) or not isinstance(value, int) or value not in (0, 1, 2):
        raise TextEvaluationError("grade must be an explicitly supplied integer 0/1/2")
    if record["provenance"] != "human_manual":
        raise TextEvaluationError("only explicitly declared human_manual judgments are accepted")
    _text(record, "rationale", allow_empty=value == 0)
    return value


def _product_id(record: Mapping[str, Any], protocol: TextEvaluationProtocol) -> str:
    value = _text(record, "product_id")
    try:
        canonical = str(UUID(value))
    except ValueError as error:
        raise TextEvaluationError(
            "product_id must be a canonical UUID, not an external ID"
        ) from error
    if canonical != value or value not in protocol.product_ids:
        raise TextEvaluationError("product_id is outside the frozen corpus")
    return value


@dataclass(frozen=True, slots=True)
class TextQuery:
    query_id: str
    query_text: str
    language_tag: str
    query_class: str
    split: str
    intent_group_id: str
    author_id: str
    authorship: str

    def record(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ConsensusJudgment:
    query_id: str
    product_id: str
    grade: int

    def record(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ValidatedJudgments:
    consensus: tuple[ConsensusJudgment, ...]
    judgments: tuple[dict[str, Any], ...]
    adjudications: tuple[dict[str, Any], ...]
    disagreement_count: int
    zero_relevance_query_ids: tuple[str, ...]
    author_adjudication_count: int


def validate_queries(
    records: Iterable[Mapping[str, Any]],
    protocol: TextEvaluationProtocol,
    *,
    require_complete: bool = True,
) -> tuple[TextQuery, ...]:
    policy = protocol.settings["queries"]
    queries = []
    identities: dict[str, int] = {}
    texts: dict[str, int] = {}
    group_splits: dict[str, str] = {}
    for position, record in enumerate(records, start=1):
        try:
            _fields(record, QUERY_FIELDS)
            values = {name: _text(record, name) for name in record}
        except TextEvaluationError as error:
            raise TextEvaluationError(f"query source row {position}: {error}") from error
        if not re.fullmatch(r"TXT-Q-[0-9]{4}", values["query_id"]) or not re.fullmatch(
            r"TXT-I-[0-9]{4}", values["intent_group_id"]
        ):
            raise TextEvaluationError(
                f"query source row {position}: invalid stable query/intent identity; "
                "expected TXT-Q-0001 / TXT-I-0001 syntax"
            )
        if (
            values["language_tag"] not in policy["language_tags"]
            or values["query_class"] not in policy["classes"]
            or values["split"] not in policy["min_per_split"]
            or values["authorship"] != "human"
        ):
            raise TextEvaluationError(
                f"query source row {position}: unsupported query language/class/split/authorship; "
                f"languages={policy['language_tags']}, classes={policy['classes']}, "
                "splits=dev/test, authorship=human"
            )
        _identifier(record, "author_id")
        if len(values["query_text"]) > policy["max_characters"]:
            raise TextEvaluationError("query exceeds protocol length limit")
        duplicate_key = normalize_text(values["query_text"]).casefold()
        if values["query_id"] in identities or duplicate_key in texts:
            previous = identities.get(values["query_id"], texts.get(duplicate_key))
            raise TextEvaluationError(
                f"duplicate query identity or normalized text at rows {previous} and {position}"
            )
        identities[values["query_id"]] = position
        texts[duplicate_key] = position
        group, split = values["intent_group_id"], values["split"]
        if group in group_splits and group_splits[group] != split:
            raise TextEvaluationError("intent-group leakage between dev and test")
        group_splits[group] = split
        queries.append(TextQuery(**values))
    if not queries:
        raise TextEvaluationError("insufficient human-authored queries: input is empty")
    result = tuple(sorted(queries, key=lambda query: query.query_id))
    issues = query_coverage(result, protocol)["issues"]
    if require_complete and issues:
        raise TextEvaluationError("; ".join(issues))
    return result


def query_coverage(
    queries: tuple[TextQuery, ...], protocol: TextEvaluationProtocol
) -> dict[str, Any]:
    policy = protocol.settings["queries"]
    issues = []
    if len(queries) < policy["min_total"]:
        issues.append(f"insufficient human-authored queries: {len(queries)}/{policy['min_total']}")
    splits = {}
    for split, minimum in policy["min_per_split"].items():
        selected = [query for query in queries if query.split == split]
        groups = len({query.intent_group_id for query in selected})
        classes = {
            name: sum(query.query_class == name for query in selected) for name in policy["classes"]
        }
        if len(selected) < minimum or any(
            count < policy["min_class_per_split"] for count in classes.values()
        ):
            issues.append(
                f"insufficient split/query-class coverage for {split}: "
                f"queries={len(selected)}/{minimum}, classes={classes}, "
                f"minimum per class={policy['min_class_per_split']}"
            )
        if groups < policy["min_intent_groups_per_split"][split]:
            issues.append(
                f"insufficient independent intent-group coverage for {split}: "
                f"{groups}/{policy['min_intent_groups_per_split'][split]}"
            )
        splits[split] = {
            "query_count": len(selected),
            "intent_group_count": groups,
            "class_counts": classes,
        }
    return {"requirements_pass": not issues, "issues": issues, "splits": splits}


def validate_judgments(
    queries: tuple[TextQuery, ...],
    records: Iterable[Mapping[str, Any]],
    adjudication_records: Iterable[Mapping[str, Any]],
    protocol: TextEvaluationProtocol,
) -> ValidatedJudgments:
    by_query = {query.query_id: query for query in queries}
    if len(by_query) != len(queries):
        raise TextEvaluationError("duplicate query identity in judgment input")
    grouped: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    query_judges: dict[str, set[str]] = defaultdict(set)
    for record in records:
        _fields(record, {"query_id", "product_id", "judge_id", "grade", "rationale", "provenance"})
        query_id = _text(record, "query_id")
        if query_id not in by_query:
            raise TextEvaluationError("judgment references an unknown query")
        product_id, judge_id = _product_id(record, protocol), _identifier(record, "judge_id")
        _grade(record)
        if judge_id == by_query[query_id].author_id:
            raise TextEvaluationError("query author cannot be a primary judge")
        key = (query_id, product_id)
        if judge_id in grouped[key]:
            raise TextEvaluationError("duplicate query/product/judge row; no silent winner")
        grouped[key][judge_id] = dict(record)
        query_judges[query_id].add(judge_id)
    expected_pairs = {
        (query_id, product_id) for query_id in by_query for product_id in protocol.product_ids
    }
    if (
        set(grouped) != expected_pairs
        or any(len(judges) != 2 for judges in grouped.values())
        or any(len(query_judges[query_id]) != 2 for query_id in by_query)
    ):
        raise TextEvaluationError("incomplete exhaustive two-judge coverage; unjudged is not zero")
    adjudications: dict[tuple[str, str], dict[str, Any]] = {}
    for record in adjudication_records:
        _fields(
            record, {"query_id", "product_id", "adjudicator_id", "grade", "rationale", "provenance"}
        )
        key = (_text(record, "query_id"), _product_id(record, protocol))
        if key not in grouped or key in adjudications:
            raise TextEvaluationError("unknown or duplicate adjudication pair")
        _grade(record)
        _text(record, "rationale")
        if _identifier(record, "adjudicator_id") in grouped[key]:
            raise TextEvaluationError("adjudicator must be a third independent human")
        if len({row["grade"] for row in grouped[key].values()}) == 1:
            raise TextEvaluationError("adjudication cannot overwrite an agreed pair")
        adjudications[key] = dict(record)
    consensus = []
    disagreement_count = author_adjudications = 0
    relevant_counts: dict[str, int] = defaultdict(int)
    for key, judges in sorted(grouped.items()):
        grades = {row["grade"] for row in judges.values()}
        if len(grades) == 1:
            grade = next(iter(grades))
        else:
            disagreement_count += 1
            if key not in adjudications:
                raise TextEvaluationError("unresolved human disagreement; adjudication required")
            grade = adjudications[key]["grade"]
            author_adjudications += (
                adjudications[key]["adjudicator_id"] == by_query[key[0]].author_id
            )
        consensus.append(ConsensusJudgment(key[0], key[1], grade))
        relevant_counts[key[0]] += grade >= 1
    for split in protocol.settings["queries"]["min_per_split"]:
        if not any(
            relevant_counts[query.query_id] > 0 for query in queries if query.split == split
        ):
            raise TextEvaluationError(
                "each split needs an answerable query; never invent relevance"
            )
    return ValidatedJudgments(
        tuple(consensus),
        tuple(row for key in sorted(grouped) for _, row in sorted(grouped[key].items())),
        tuple(adjudications[key] for key in sorted(adjudications)),
        disagreement_count,
        tuple(query_id for query_id in sorted(by_query) if not relevant_counts[query_id]),
        author_adjudications,
    )
