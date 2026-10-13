from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

import numpy as np

from .errors import DenseRetrieverError

_TOY_KEYWORDS = ("red", "blue", "black")


@runtime_checkable
class TextEncoder(Protocol):
    @property
    def encoder_id(self) -> str: ...

    @property
    def encoder_revision(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        """Return shape (len(texts), dimension) float32 unit vectors."""


def _l2_normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if np.any(norms == 0):
        raise DenseRetrieverError("encoder produced a zero-norm vector")
    return matrix / norms


class ToyTextEncoder:
    """Deterministic toy vectors for prototype engineering; not semantic production quality."""

    def __init__(self, *, dimension: int = 3) -> None:
        if isinstance(dimension, bool) or not isinstance(dimension, int) or dimension != 3:
            raise DenseRetrieverError("ToyTextEncoder prototype dimension must be 3")
        self._dimension = dimension

    @property
    def encoder_id(self) -> str:
        return "toy-text-encoder-v1"

    @property
    def encoder_revision(self) -> str:
        return "deterministic-keyword-v1"

    @property
    def dimension(self) -> int:
        return self._dimension

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            raise DenseRetrieverError("encode requires at least one text")
        matrix = np.zeros((len(texts), self._dimension), dtype=np.float64)
        for row, text in enumerate(texts):
            if not isinstance(text, str) or not text.strip():
                raise DenseRetrieverError("encode text must be nonblank")
            lowered = text.casefold()
            for index, keyword in enumerate(_TOY_KEYWORDS):
                if keyword in lowered:
                    matrix[row, index] += 1.0
            if matrix[row].sum() == 0:
                raise DenseRetrieverError(
                    "toy encoder requires red/blue/black keyword signal in text"
                )
        return _l2_normalize(matrix).astype(np.float32)


def create_prototype_encoder(config_dimension: int) -> TextEncoder:
    if config_dimension == 3:
        return ToyTextEncoder(dimension=config_dimension)
    raise DenseRetrieverError("only ToyTextEncoder is implemented in the prototype gate")
