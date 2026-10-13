pytest_plugins = ["tests.database.conftest"]

from collections.abc import Sequence

import numpy as np
import pytest
from PIL import Image

from sahulat_visual.domain import EncoderIdentity, Vectors, normalize
from sahulat_visual.encoders.base import VisualEncoder


class FixtureEncoder(VisualEncoder):
    """Deterministic RGB test double; never a research model or benchmark result."""

    identity = EncoderIdentity("fixture", "test-v1", "none", "rgb-mean", 3, "fixture-v1")
    device = "cpu"
    load_time_ms = 0.0

    def encode_images(self, images: Sequence[Image.Image]) -> Vectors:
        return normalize(
            np.array([np.asarray(image).mean(axis=(0, 1)) for image in images], dtype=np.float32)
        )


@pytest.fixture
def encoder():
    return FixtureEncoder()


@pytest.fixture
def image_file(tmp_path):
    def create(name, color=(200, 30, 10), format="PNG"):
        path = tmp_path / name
        Image.new("RGB", (32, 32), color).save(path, format=format)
        return path

    return create
