import os
from dataclasses import dataclass

from .errors import ConfigurationError


@dataclass(frozen=True)
class Settings:
    model: str = "openclip"
    device: str = "auto"
    batch_size: int = 16
    num_workers: int = 0
    product_top_k: int = 5
    image_top_k: int = 25
    cache_dir: str = ".cache/models"

    def __post_init__(self) -> None:
        if self.model not in {"openclip", "fashionclip"}:
            raise ConfigurationError(f"Unsupported visual model: {self.model}")
        for key in ("batch_size", "product_top_k", "image_top_k"):
            if getattr(self, key) < 1:
                raise ConfigurationError(f"{key} must be positive")
        if self.num_workers < 0:
            raise ConfigurationError("num_workers cannot be negative")

    @classmethod
    def from_env(cls) -> "Settings":
        try:
            return cls(
                model=os.getenv("VISUAL_MODEL", "openclip"),
                device=os.getenv("VISUAL_DEVICE", "auto"),
                batch_size=int(os.getenv("VISUAL_BATCH_SIZE", "16")),
                num_workers=int(os.getenv("VISUAL_NUM_WORKERS", "0")),
                product_top_k=int(os.getenv("VISUAL_PRODUCT_TOP_K", "5")),
                image_top_k=int(os.getenv("VISUAL_IMAGE_TOP_K", "25")),
                cache_dir=os.getenv("VISUAL_CACHE_DIR", ".cache/models"),
            )
        except ValueError as exc:
            raise ConfigurationError("Visual numeric configuration must contain integers") from exc
