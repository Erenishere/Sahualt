import json
import os
import tempfile
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any, Protocol
from zipfile import BadZipFile

import numpy as np

from .domain import EncoderIdentity, ImageMatch, ImageRecord, Vectors, normalize, positive_k
from .errors import EmptyIndexError, IndexCompatibilityError


class VectorIndex(Protocol):
    identity: EncoderIdentity

    @property
    def count(self) -> int: ...

    def search(
        self, vector: Vectors, top_k: int, identity: EncoderIdentity
    ) -> list[ImageMatch]: ...


class InMemoryVectorIndex:
    """Exact normalized inner product, equal to cosine similarity; larger is better.

    Immutable after construction. Build a replacement snapshot to update a catalogue.
    """

    def __init__(
        self,
        identity: EncoderIdentity,
        vectors: Vectors,
        records: Sequence[ImageRecord],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        values = np.asarray(vectors, dtype=np.float32)
        if values.shape != (len(records), identity.embedding_dimension):
            raise IndexCompatibilityError("Index vector dimensions do not match metadata")
        if len({r.image_id for r in records}) != len(records):
            raise IndexCompatibilityError("Index image IDs must be unique")
        order = sorted(range(len(records)), key=lambda i: records[i].image_id)
        self._records = tuple(records[i] for i in order)
        self._vectors = normalize(values[order]).copy()
        self._vectors.flags.writeable = False
        self.identity = identity
        self.metadata = dict(metadata or {})

    @property
    def count(self) -> int:
        return len(self._records)

    def search(self, vector: Vectors, top_k: int, identity: EncoderIdentity) -> list[ImageMatch]:
        positive_k(top_k)
        if identity != self.identity:
            raise IndexCompatibilityError(
                "Query and index encoder identities differ; rebuild index"
            )
        if np.asarray(vector).shape != (self.identity.embedding_dimension,):
            raise IndexCompatibilityError("Query vector dimension mismatch")
        if not self.count:
            raise EmptyIndexError("No catalogue vectors are indexed")
        scores = np.clip(self._vectors @ normalize(vector), -1.0, 1.0)
        # Stable sorting makes tied scores reproducible by image ID.
        order = np.argsort(-scores, kind="stable")[:top_k]
        return [ImageMatch(self._records[i], float(scores[i])) for i in order]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "format_version": 1,
            "identity": self.identity.to_dict(),
            "metadata": self.metadata,
            "records": [asdict(r) for r in self._records],
        }
        fd, name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as stream:
                np.savez_compressed(
                    stream,
                    vectors=self._vectors,
                    metadata=np.array(json.dumps(payload, allow_nan=False)),
                )
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)

    @classmethod
    def load(cls, path: Path) -> "InMemoryVectorIndex":
        try:
            with np.load(path, allow_pickle=False) as archive:
                payload = json.loads(str(archive["metadata"]))
                if payload["format_version"] != 1:
                    raise IndexCompatibilityError("Unsupported index file version")
                return cls(
                    EncoderIdentity(**payload["identity"]),
                    archive["vectors"],
                    [ImageRecord(**r) for r in payload["records"]],
                    payload["metadata"],
                )
        except (OSError, ValueError, KeyError, TypeError, BadZipFile) as exc:
            raise IndexCompatibilityError("Cannot read valid index artifact") from exc
