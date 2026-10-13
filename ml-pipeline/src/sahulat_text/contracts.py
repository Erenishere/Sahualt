from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class SourceRank:
    """A branch rank retained as evidence for fusion and diagnostics."""

    source: str
    rank: int

    def __post_init__(self) -> None:
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source must be a non-empty string")
        if isinstance(self.rank, bool) or not isinstance(self.rank, int) or self.rank < 1:
            raise ValueError("rank must be a positive integer")


@dataclass(frozen=True, slots=True)
class TextMatch:
    """A product-level text result; score is not a calibrated probability."""

    product_id: str
    score: float
    source_ranks: tuple[SourceRank, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.product_id, str) or not self.product_id.strip():
            raise ValueError("product_id must be a non-empty string")
        if isinstance(self.score, bool) or not isinstance(self.score, (int, float)):
            raise ValueError("score must be a finite number")
        if not isfinite(self.score):
            raise ValueError("score must be a finite number")
        if not isinstance(self.source_ranks, tuple):
            raise ValueError("source_ranks must be an immutable tuple")
        sources = [item.source for item in self.source_ranks]
        if len(sources) != len(set(sources)):
            raise ValueError("source_ranks must contain each source at most once")


@runtime_checkable
class TextRetriever(Protocol):
    """Stable contract implemented independently by Baselines A, B, and D."""

    @property
    def retriever_id(self) -> str:
        """Return the versioned retriever identity."""
        ...

    @property
    def index_version(self) -> str:
        """Return the immutable index/document compatibility identity."""
        ...

    def search(self, query: str, top_k: int) -> Sequence[TextMatch]:
        """Return unique products ordered from most to least relevant."""
        ...
