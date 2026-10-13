"""Baseline A lexical retrieval prototype (PostgreSQL FTS)."""

from .config import LexicalRetrieverConfig, load_prototype_config
from .corpus_load import load_lexical_documents_from_registry, toy_lexical_documents
from .errors import LexicalRetrieverError
from .index import LexicalIndexDocument, documents_from_product_text, rebuild_lexical_index
from .retriever import PostgresLexicalRetriever

__all__ = [
    "LexicalIndexDocument",
    "LexicalRetrieverConfig",
    "LexicalRetrieverError",
    "PostgresLexicalRetriever",
    "documents_from_product_text",
    "load_lexical_documents_from_registry",
    "load_prototype_config",
    "rebuild_lexical_index",
    "toy_lexical_documents",
]
