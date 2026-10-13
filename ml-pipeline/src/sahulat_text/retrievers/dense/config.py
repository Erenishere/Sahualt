from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_PROTOTYPE_CONFIG = Path("configs/dense_retriever_prototype_v1.yaml")


@dataclass(frozen=True, slots=True)
class DenseRetrieverConfig:
    version: str
    migration_id: str
    retriever_id: str
    encoder_id: str
    encoder_revision: str
    vector_dimension: int
    similarity_metric: str
    search_policy: str
    normalization: str
    document_schema_version: str

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> DenseRetrieverConfig:
        required = (
            "version",
            "migration_id",
            "retriever_id",
            "encoder_id",
            "encoder_revision",
            "vector_dimension",
            "similarity_metric",
            "search_policy",
            "normalization",
            "document_schema_version",
        )
        missing = [name for name in required if name not in data]
        if missing:
            raise ValueError(f"dense config missing keys: {missing}")
        dimension = data["vector_dimension"]
        if isinstance(dimension, bool) or not isinstance(dimension, int) or dimension < 1:
            raise ValueError("vector_dimension must be a positive integer")
        if data["similarity_metric"] != "cosine":
            raise ValueError("prototype supports cosine similarity only")
        if data["search_policy"] != "exact_pgvector_scan":
            raise ValueError("prototype supports exact_pgvector_scan only")
        if data["normalization"] != "l2_unit":
            raise ValueError("prototype supports l2_unit normalization only")
        return cls(
            str(data["version"]),
            str(data["migration_id"]),
            str(data["retriever_id"]),
            str(data["encoder_id"]),
            str(data["encoder_revision"]),
            dimension,
            str(data["similarity_metric"]),
            str(data["search_policy"]),
            str(data["normalization"]),
            str(data["document_schema_version"]),
        )


def load_prototype_config(path: Path = DEFAULT_PROTOTYPE_CONFIG) -> DenseRetrieverConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("dense prototype config must be a mapping")
    return DenseRetrieverConfig.from_mapping(data)
