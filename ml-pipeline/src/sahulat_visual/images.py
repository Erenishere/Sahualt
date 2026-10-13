import hashlib
import io
import warnings
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from .errors import ConfigurationError, InvalidImageError


@dataclass(frozen=True)
class ImagePolicy:
    max_bytes: int = 20 * 1024 * 1024
    max_pixels: int = 25_000_000
    min_side: int = 16
    max_side: int = 12000
    allowed_formats: tuple[str, ...] = ("JPEG", "PNG", "WEBP")

    def __post_init__(self) -> None:
        if min(self.max_bytes, self.max_pixels, self.min_side, self.max_side) < 1:
            raise ConfigurationError("Image limits must be positive")
        if self.min_side > self.max_side or not self.allowed_formats:
            raise ConfigurationError("Image dimension/format policy is inconsistent")


DEFAULT_POLICY = ImagePolicy()


def read_bytes(path: Path, policy: ImagePolicy) -> bytes:
    try:
        with path.open("rb") as stream:
            content = stream.read(policy.max_bytes + 1)
    except OSError as exc:
        raise InvalidImageError(f"Cannot read image: {path.name}") from exc
    return content


def load_image(source: Path | bytes, policy: ImagePolicy = DEFAULT_POLICY) -> Image.Image:
    content = read_bytes(source, policy) if isinstance(source, Path) else source
    if not content or len(content) > policy.max_bytes:
        raise InvalidImageError("Image is empty or exceeds the byte limit")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as probe:
                if probe.format not in policy.allowed_formats:
                    raise InvalidImageError("Unsupported decoded image format")
                width, height = probe.size
                if (
                    min(width, height) < policy.min_side
                    or max(width, height) > policy.max_side
                    or width * height > policy.max_pixels
                ):
                    raise InvalidImageError("Image dimensions exceed the configured bounds")
                if getattr(probe, "n_frames", 1) != 1:
                    raise InvalidImageError("Animated images are not supported")
                probe.verify()
            with Image.open(io.BytesIO(content)) as decoded:
                return ImageOps.exif_transpose(decoded).convert("RGB")
    except InvalidImageError:
        raise
    except (
        OSError,
        SyntaxError,
        ValueError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise InvalidImageError("Image cannot be decoded safely") from exc


def pixel_hash(image: Image.Image) -> str:
    digest = hashlib.sha256(f"RGB:{image.width}:{image.height}:".encode())
    digest.update(image.tobytes())
    return digest.hexdigest()
