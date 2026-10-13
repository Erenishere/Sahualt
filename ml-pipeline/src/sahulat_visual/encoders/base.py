from abc import ABC, abstractmethod
from collections.abc import Sequence

from PIL import Image

from ..domain import EncoderIdentity, Vectors


class VisualEncoder(ABC):
    identity: EncoderIdentity
    device: str
    load_time_ms: float

    @property
    def embedding_dimension(self) -> int:
        return self.identity.embedding_dimension

    @property
    def model_name(self) -> str:
        return self.identity.model_name

    @property
    def model_version(self) -> str:
        return self.identity.model_version

    def encode_image(self, image: Image.Image) -> Vectors:
        return self.encode_images([image])[0]

    @abstractmethod
    def encode_images(self, images: Sequence[Image.Image]) -> Vectors:
        """Return finite L2-normalized float32 embeddings in input order."""

    def synchronize(self) -> None:
        """Finish pending device work; CPU encoders execute synchronously by default."""
        return None
