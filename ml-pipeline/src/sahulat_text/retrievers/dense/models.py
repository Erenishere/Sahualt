from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

from .errors import DenseRetrieverError

_CORPUS_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class DenseIndexRecord:
    product_id: UUID
    embedding: tuple[float, ...]
    corpus_sha256: str
    document_schema_version: str
    encoder_id: str
    encoder_revision: str

    def __post_init__(self) -> None:
        if not _CORPUS_SHA256.fullmatch(self.corpus_sha256):
            raise DenseRetrieverError("corpus_sha256 must be lowercase sha256 hex")
        if not self.embedding:
            raise DenseRetrieverError("embedding must be non-empty")
        if any(not isinstance(value, (int, float)) for value in self.embedding):
            raise DenseRetrieverError("embedding components must be numeric")
