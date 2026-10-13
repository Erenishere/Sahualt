import os

import numpy as np
import pytest
from PIL import Image

from sahulat_visual.config import Settings
from sahulat_visual.encoders.factory import create_encoder

pytestmark = [pytest.mark.model, pytest.mark.slow]


@pytest.mark.skipif(
    os.getenv("RUN_MODEL_TESTS") != "1", reason="Set RUN_MODEL_TESTS=1 for pretrained tests"
)
@pytest.mark.parametrize("model", ["openclip", "fashionclip"])
def test_pretrained_batch_and_query_agree(model):
    encoder = create_encoder(Settings(model=model))
    image = Image.new("RGB", (224, 224), (180, 60, 30))
    single = encoder.encode_image(image)
    batch = encoder.encode_images([image, image])
    assert batch.shape == (2, 512)
    assert np.isfinite(batch).all()
    np.testing.assert_allclose(np.linalg.norm(batch, axis=1), 1, atol=1e-6)
    np.testing.assert_allclose(single, batch[0], atol=2e-5)
