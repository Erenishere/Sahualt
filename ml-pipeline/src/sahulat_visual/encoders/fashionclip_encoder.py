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


class FashionCLIPEncoder(VisualEncoder):
    def __init__(self, settings: Settings, spec: dict[str, str]) -> None:
        start = perf_counter()
        from huggingface_hub import snapshot_download
        from transformers import CLIPImageProcessor, CLIPVisionModelWithProjection

        self.device = select_device(settings.device)
        snapshot = snapshot_download(
            spec["identifier"],
            revision=spec["revision"],
            cache_dir=settings.cache_dir,
            allow_patterns=[spec["weights_file"], "config.json", "preprocessor_config.json"],
        )
        self._processor = CLIPImageProcessor.from_pretrained(snapshot, local_files_only=True)
        # The vision projection is required; hidden-state pooling is not the CLIP embedding.
        self._model = CLIPVisionModelWithProjection.from_pretrained(
            snapshot,
            local_files_only=True,
            use_safetensors=True,
        ).to(self.device)
        self._model.eval().requires_grad_(False)
        self.identity = identity(
            "fashionclip",
            spec,
            read_json(Path(snapshot) / "preprocessor_config.json"),
            self._model.config.projection_dim,
            ["transformers", "torch", "torchvision", "Pillow", "numpy"],
        )
        self.synchronize()
        self.load_time_ms = (perf_counter() - start) * 1000

    def encode_images(self, images: Sequence[Image.Image]) -> Vectors:
        import torch

        if not images:
            return np.empty((0, self.embedding_dimension), dtype=np.float32)
        with torch.inference_mode():
            pixels = self._processor(
                images=[im.convert("RGB") for im in images], return_tensors="pt"
            )["pixel_values"].to(self.device)
            features = self._model(pixel_values=pixels).image_embeds
            return normalize(features.float().cpu().numpy())

    def synchronize(self) -> None:
        synchronize(self.device)
