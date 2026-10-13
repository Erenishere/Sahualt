from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from .errors import IndexCompatibilityError

Vectors = NDArray[np.float32]


def positive_k(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("top_k must be a positive integer")
    return value


def normalize(vectors: Vectors) -> Vectors:
    values = np.asarray(vectors, dtype=np.float32)
    if values.ndim not in (1, 2) or not np.isfinite(values).all():
        raise IndexCompatibilityError("Embeddings must be finite vectors or a matrix")
    # Compute norms in float64 to avoid float32 overflow/underflow.
    norms = np.linalg.norm(values.astype(np.float64), axis=-1, keepdims=True)
    if np.any(norms <= 0):
        raise IndexCompatibilityError("Zero embeddings cannot be normalized")
    return (values / norms).astype(np.float32)


@dataclass(frozen=True)
class ImageRecord:
    image_id: str
    product_id: str
    image_path: str

    def __post_init__(self) -> None:
        if not all(isinstance(v, str) and v.strip() for v in asdict(self).values()):
            raise ValueError("image_id, product_id and image_path must be non-empty strings")


@dataclass(frozen=True)
class EncoderIdentity:
    model_name: str
    model_version: str
    weights: str
    preprocessing: str
    embedding_dimension: int
    embedding_version: str

    def __post_init__(self) -> None:
        if self.embedding_dimension < 1 or not all(
            isinstance(v, str) and v.strip()
            for k, v in asdict(self).items()
            if k != "embedding_dimension"
        ):
            raise IndexCompatibilityError("Invalid encoder identity")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ImageMatch:
    record: ImageRecord
    score: float


@dataclass(frozen=True)
class ProductMatch:
    product_id: str
    score: float
    matched_image_id: str
    matched_image_path: str
