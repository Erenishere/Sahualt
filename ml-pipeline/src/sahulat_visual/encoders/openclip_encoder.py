from collections.abc import Sequence
from pathlib import Path
from time import perf_counter

import numpy as np
from PIL import Image

from ..config import Settings
from ..domain import Vectors, normalize
from ..io import read_json
from .base import VisualEncoder
from .runtime import identity, select_device, synchronize


class OpenCLIPEncoder(VisualEncoder):
    def __init__(self, settings: Settings, spec: dict[str, str]) -> None:
        start = perf_counter()
        import open_clip
        from huggingface_hub import snapshot_download

        self.device = select_device(settings.device)
        snapshot = snapshot_download(
            spec["identifier"],
            revision=spec["revision"],
            cache_dir=settings.cache_dir,
            allow_patterns=[spec["weights_file"], "open_clip_config.json"],
        )
        # local-dir loads both checkpoint and its own preprocessing config at the pinned revision.
        self._model, _, self._preprocess = open_clip.create_model_and_transforms(
            f"local-dir:{snapshot}",
            device=self.device,
            precision="fp32",
        )
        self._model.eval().requires_grad_(False)
        self.identity = identity(
            "openclip",
            spec,
            {
                "checkpoint_config": read_json(Path(snapshot) / "open_clip_config.json"),
                # Transform repr can contain process-specific function addresses.
                "transform": "create_model_and_transforms-eval-defaults-v1",
            },
            self._model.visual.output_dim,
            ["open_clip_torch", "torch", "torchvision", "Pillow", "numpy"],
        )
        self.synchronize()
        self.load_time_ms = (perf_counter() - start) * 1000

    def encode_images(self, images: Sequence[Image.Image]) -> Vectors:
        import torch

        if not images:
            return np.empty((0, self.embedding_dimension), dtype=np.float32)
        with torch.inference_mode():
            batch = torch.stack([self._preprocess(image.convert("RGB")) for image in images])
            features = self._model.encode_image(batch.to(self.device))
            return normalize(features.float().cpu().numpy())

    def synchronize(self) -> None:
        synchronize(self.device)
