import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

import numpy as np
from PIL import Image

from .dataset import resolve_image
from .domain import ImageRecord, Vectors
from .encoders.base import VisualEncoder
from .errors import DatasetError
from .images import DEFAULT_POLICY, ImagePolicy, load_image, pixel_hash


@dataclass
class EmbeddingRun:
    vectors: Vectors
    total_ms: float
    batch_amortized_image_ms: list[float]


def embed_catalogue(
    encoder: VisualEncoder,
    records: list[ImageRecord],
    root: Path,
    batch_size: int = 16,
    num_workers: int = 0,
    policy: ImagePolicy = DEFAULT_POLICY,
    expected_hashes: dict[str, str] | None = None,
) -> EmbeddingRun:
    if batch_size < 1 or num_workers < 0:
        raise ValueError("Invalid batching configuration")
    vectors = np.empty((len(records), encoder.embedding_dimension), dtype=np.float32)
    samples = []
    start = perf_counter()
    # Workers only decode one bounded batch; model execution stays on the calling thread.
    with ThreadPoolExecutor(max_workers=max(1, num_workers)) as pool:
        for offset in range(0, len(records), batch_size):
            batch_start = perf_counter()
            batch = records[offset : offset + batch_size]
            paths = [resolve_image(root, r.image_path) for r in batch]
            images: list[Image.Image] = []
            try:
                if num_workers:
                    futures = [pool.submit(load_image, path, policy) for path in paths]
                    # Consume every future so images are closed even after a decoding failure.
                    error = None
                    for future in futures:
                        try:
                            images.append(future.result())
                        except Exception as exc:
                            error = exc
                    if error is not None:
                        raise error
                else:
                    for path in paths:
                        images.append(load_image(path, policy))
                if expected_hashes is not None:
                    for record, image in zip(batch, images, strict=True):
                        if pixel_hash(image) != expected_hashes[record.image_id]:
                            raise DatasetError(f"Image changed after audit: {record.image_id}")
                encoded = encoder.encode_images(images)
                if encoded.shape != (len(batch), encoder.embedding_dimension):
                    raise DatasetError("Encoder returned an incorrect batch shape")
                vectors[offset : offset + len(batch)] = encoded
                encoder.synchronize()
            finally:
                for image in images:
                    image.close()
            elapsed = (perf_counter() - batch_start) * 1000
            samples.extend([elapsed / len(batch)] * len(batch))
            logging.getLogger(__name__).info(
                "embedding_batch_completed",
                extra={
                    "completed": offset + len(batch),
                    "total": len(records),
                    "batch_ms": elapsed,
                },
            )
    return EmbeddingRun(vectors, (perf_counter() - start) * 1000, samples)
