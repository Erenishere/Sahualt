"""Baseline D text-only reciprocal-rank fusion."""

from .config import HybridRetrieverConfig, load_prototype_config
from .errors import HybridRetrieverError
from .rank_fusion import reciprocal_rank_fusion
from .retriever import HybridRRFRetriever

__all__ = [
    "HybridRRFRetriever",
    "HybridRetrieverConfig",
    "HybridRetrieverError",
    "load_prototype_config",
    "reciprocal_rank_fusion",
]
