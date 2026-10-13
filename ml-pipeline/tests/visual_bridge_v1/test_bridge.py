import asyncio
import io
from dataclasses import replace

import httpx
import numpy as np
import pytest
from PIL import Image

from integration.visual_bridge_v1.bridge import VisualIntegrationBridge
from integration.visual_bridge_v1.catalogue import resolve_snapshot
from integration.visual_bridge_v1.errors import BridgeError
from sahulat_api.app import create_app
from sahulat_api.settings import HttpSettings
from sahulat_visual.domain import ImageRecord
from sahulat_visual.index import InMemoryVectorIndex
from sahulat_visual.retrieval import VisualRetrievalService
from tests.visual_bridge_v1.test_catalogue import snapshot
from tests.visual_bridge_v1.test_client import client, search_payload

pytestmark = pytest.mark.integration


class SnapshotReader:
    def __init__(self):
        self.calls = 0

    async def resolve(self, search):
        self.calls += 1
        return resolve_snapshot(search, snapshot())


def test_actual_fastapi_service_to_app_bridge_synthetic_catalogue(encoder):
    encoder.identity = replace(
        encoder.identity, model_name="openclip", embedding_version="synthetic-openclip-v1"
    )
    index = InMemoryVectorIndex(
        encoder.identity,
        np.array([[1, 0, 0], [0.8, 0.6, 0]]),
        [
            ImageRecord("A/image_1.png", "A", "private/a.png"),
            ImageRecord("B/image_1.png", "B", "private/b.png"),
        ],
        {"dataset_version": "synthetic-v1"},
    )
    app = create_app(
        HttpSettings("synthetic-v1"), service_factory=lambda: VisualRetrievalService(encoder, index)
    )
    image = io.BytesIO()
    Image.new("RGB", (32, 32), (255, 0, 0)).save(image, format="PNG")

    async def scenario():
        async with app.router.lifespan_context(app):
            async with client(httpx.ASGITransport(app)) as api:
                await api.health()
                await api.readiness()
                output = await VisualIntegrationBridge(api, SnapshotReader()).search(
                    image.getvalue(), mime_type="image/png"
                )
                assert [r.external_product_id for r in output] == ["A", "B"]
                assert [r.rank for r in output] == [1, 2]
                assert output[0].score == 1
                assert output[0].product.name == "Synthetic A"

    asyncio.run(scenario())


def test_api_failure_never_contacts_catalogue():
    reader = SnapshotReader()

    async def scenario():
        async with client(
            httpx.MockTransport(
                lambda r: httpx.Response(
                    503, json={"error": {"code": "visual_unavailable", "message": "private"}}
                )
            )
        ) as api:
            with pytest.raises(BridgeError, match="api_unavailable"):
                await VisualIntegrationBridge(api, reader).search(b"image", mime_type="image/png")

    asyncio.run(scenario())
    assert reader.calls == 0


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("rerank", "ranking_violation"),
        ("score", "ranking_violation"),
        ("omit", "canonical_resolution_failure"),
        ("duplicate", "ambiguous_identity"),
    ],
)
def test_bridge_rejects_any_catalogue_reranking_or_identity_drift(mode, expected):
    class WrongReader(SnapshotReader):
        async def resolve(self, search):
            result = list(await super().resolve(search))
            if mode == "rerank":
                result.reverse()
            elif mode == "score":
                result[0] = replace(result[0], score=0.1)
            elif mode == "omit":
                result.pop()
            else:
                result[1] = replace(result[1], product=result[0].product)
            return tuple(result)

    async def scenario():
        async with client(
            httpx.MockTransport(lambda r: httpx.Response(200, json=search_payload()))
        ) as api:
            with pytest.raises(BridgeError, match=expected):
                await VisualIntegrationBridge(api, WrongReader()).search(
                    b"image", mime_type="image/png"
                )

    asyncio.run(scenario())
