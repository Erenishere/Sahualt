"""Baseline B dense text retrieval prototype (pgvector + TextEncoder)."""

from .config import DenseRetrieverConfig, load_prototype_config
from .encoder import TextEncoder, ToyTextEncoder, create_prototype_encoder
from .errors import DenseRetrieverError
from .models import DenseIndexRecord
from .repository import rebuild_dense_index, records_from_searchable_texts
from .retriever import PostgresDenseRetriever

__all__ = [
    "DenseIndexRecord",
    "DenseRetrieverConfig",
    "DenseRetrieverError",
    "PostgresDenseRetriever",
    "TextEncoder",
    "ToyTextEncoder",
    "create_prototype_encoder",
    "load_prototype_config",
    "rebuild_dense_index",
    "records_from_searchable_texts",
]
