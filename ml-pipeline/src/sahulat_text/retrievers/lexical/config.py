from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_PROTOTYPE_CONFIG = Path("configs/lexical_retriever_prototype_v1.yaml")


@dataclass(frozen=True, slots=True)
class LexicalRetrieverConfig:
    version: str
    migration_id: str
    text_search_config: str
    query_parser: str
    rank_function: str
    document_schema_version: str
    retriever_id: str

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> LexicalRetrieverConfig:
        required = (
            "version",
            "migration_id",
            "text_search_config",
            "query_parser",
            "rank_function",
            "document_schema_version",
            "retriever_id",
        )
        missing = [name for name in required if not data.get(name)]
        if missing:
            raise ValueError(f"lexical config missing keys: {missing}")
        if data.get("query_parser") != "websearch_to_tsquery":
            raise ValueError("prototype supports websearch_to_tsquery only")
        if data.get("rank_function") != "ts_rank_cd":
            raise ValueError("prototype supports ts_rank_cd only")
        if data.get("text_search_config") != "english":
            raise ValueError("prototype supports english text_search_config only")
        return cls(
            str(data["version"]),
            str(data["migration_id"]),
            str(data["text_search_config"]),
            str(data["query_parser"]),
            str(data["rank_function"]),
            str(data["document_schema_version"]),
            str(data["retriever_id"]),
        )


def load_prototype_config(path: Path = DEFAULT_PROTOTYPE_CONFIG) -> LexicalRetrieverConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("lexical prototype config must be a mapping")
    return LexicalRetrieverConfig.from_mapping(data)
