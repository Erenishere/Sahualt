import logging

from ..config import Settings
from ..errors import ConfigurationError, ModelLoadError
from .base import VisualEncoder

MODEL_SPECS = {
    "openclip": {
        "identifier": "laion/CLIP-ViT-B-32-laion2B-s34B-b79K",
        "revision": "1a25a446712ba5ee05982a381eed697ef9b435cf",
        "architecture": "ViT-B-32",
        "weights_file": "open_clip_model.safetensors",
    },
    "fashionclip": {
        "identifier": "patrickjohncyh/fashion-clip",
        "revision": "7e3ba62ce16b379a1ab479346b66f192e76f51b7",
        "architecture": "ViT-B-32",
        "weights_file": "model.safetensors",
    },
}


def create_encoder(settings: Settings) -> VisualEncoder:
    from .fashionclip_encoder import FashionCLIPEncoder
    from .openclip_encoder import OpenCLIPEncoder

    registry = {"openclip": OpenCLIPEncoder, "fashionclip": FashionCLIPEncoder}
    if settings.model not in registry:
        raise ConfigurationError(f"Unsupported model: {settings.model}")
    try:
        encoder = registry[settings.model](settings, MODEL_SPECS[settings.model])
    except ConfigurationError:
        raise
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        raise ModelLoadError(
            f"Could not load {settings.model}; install the ml extra and check weight availability"
        ) from exc
    logging.getLogger(__name__).info(
        "model_loaded",
        extra={
            **encoder.identity.to_dict(),
            "device": encoder.device,
            "model_loading_ms": encoder.load_time_ms,
        },
    )
    return encoder
