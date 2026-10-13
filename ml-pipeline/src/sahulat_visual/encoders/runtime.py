import importlib.metadata
from typing import Any

from ..domain import EncoderIdentity
from ..errors import ConfigurationError
from ..io import content_hash


def select_device(requested: str) -> str:
    import torch

    if requested == "auto":
        if torch.cuda.is_available():
            return "cuda"
        if torch.backends.mps.is_available():
            return "mps"
        if hasattr(torch, "xpu") and torch.xpu.is_available():
            return "xpu"
        return "cpu"
    try:
        device = torch.device(requested)
        if device.type not in {"cpu", "cuda", "mps", "xpu"}:
            raise ValueError("Unsupported device")
        torch.empty(1, device=device)
    except (RuntimeError, ValueError, AssertionError, IndexError) as exc:
        raise ConfigurationError(f"Requested device is unavailable: {requested}") from exc
    return str(device)


def synchronize(device: str) -> None:
    import torch

    kind = torch.device(device).type
    if kind == "cuda":
        torch.cuda.synchronize(device)
    elif kind == "mps":
        torch.mps.synchronize()
    elif kind == "xpu":
        torch.xpu.synchronize(device)


def identity(
    name: str, spec: dict[str, str], preprocessing: Any, dimension: int, packages: list[str]
) -> EncoderIdentity:
    dependencies = {p: importlib.metadata.version(p) for p in packages}
    preprocess_hash = content_hash(
        {
            "config": preprocessing,
            "dependencies": dependencies,
            "input": "exif-transpose-rgb-v1",
            "dtype": "fp32",
            "normalization": "l2-float64-norm-float32-output-v1",
        }
    )
    return EncoderIdentity(
        model_name=name,
        model_version=spec["revision"],
        weights=f"{spec['identifier']}@{spec['revision']}/{spec['weights_file']}",
        preprocessing=preprocess_hash,
        embedding_dimension=dimension,
        embedding_version=f"{name}-vit-b32-{spec['revision'][:12]}-{preprocess_hash[:12]}-v1",
    )
