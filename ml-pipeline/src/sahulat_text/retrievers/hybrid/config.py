from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_PROTOTYPE_CONFIG = Path("configs/hybrid_retriever_prototype_v1.yaml")


@dataclass(frozen=True, slots=True)
class HybridRetrieverConfig:
    version: str
    retriever_id: str
    rrf_k: int
    lexical_branch_source: str
    dense_branch_source: str
    branch_depth: int
    document_schema_version: str

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> HybridRetrieverConfig:
        required = (
            "version",
            "retriever_id",
            "rrf_k",
            "lexical_branch_source",
            "dense_branch_source",
            "branch_depth",
            "document_schema_version",
        )
        missing = [name for name in required if data.get(name) is None]
        if missing:
            raise ValueError(f"hybrid config missing keys: {missing}")
        rrf_k = data["rrf_k"]
        branch_depth = data["branch_depth"]
        if isinstance(rrf_k, bool) or not isinstance(rrf_k, int) or rrf_k < 1:
            raise ValueError("rrf_k must be a positive integer")
        if isinstance(branch_depth, bool) or not isinstance(branch_depth, int) or branch_depth < 1:
            raise ValueError("branch_depth must be a positive integer")
        return cls(
            str(data["version"]),
            str(data["retriever_id"]),
            int(rrf_k),
            str(data["lexical_branch_source"]),
            str(data["dense_branch_source"]),
            int(branch_depth),
            str(data["document_schema_version"]),
        )


def load_prototype_config(
    path: Path = DEFAULT_PROTOTYPE_CONFIG,
) -> HybridRetrieverConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("hybrid prototype config must be a mapping")
    return HybridRetrieverConfig.from_mapping(data)
