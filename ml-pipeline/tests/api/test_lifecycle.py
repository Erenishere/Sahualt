import asyncio
import hashlib
import threading

import httpx
import pytest

from sahulat_api.app import create_app, load_visual_service
from sahulat_api.cli import main
from sahulat_api.settings import HttpSettings
from sahulat_visual.errors import IndexCompatibilityError
from tests.api.test_visual_http import image_bytes, service

registered_fixture = service
pytestmark = pytest.mark.unit


def test_cached_asset_loading_checks_checksum_namespace_and_offline(service, tmp_path, monkeypatch):
    path = tmp_path / "index.npz"
    service.index.save(path)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    settings = HttpSettings("synthetic-v1", index_path=path, index_sha256=sha)
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    with pytest.raises(ValueError, match="HF_HUB_OFFLINE"):
        load_visual_service(settings)
    calls = []

    def encoder_factory(settings):
        calls.append(1)
        return service.encoder

    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setattr("sahulat_visual.encoders.factory.create_encoder", encoder_factory)
    loaded = load_visual_service(settings)
    assert loaded.index.count == 3 and calls == [1]
    with pytest.raises(IndexCompatibilityError):
        load_visual_service(HttpSettings("other-v1", index_path=path, index_sha256=sha))
    assert calls == [1]


def test_cancellation_does_not_release_running_model_slot(service, monkeypatch):
    started, release = threading.Event(), threading.Event()
    original = service.search

    def blocked(*args, **kwargs):
        started.set()
        assert release.wait(timeout=5)
        return original(*args, **kwargs)

    monkeypatch.setattr(service, "search", blocked)
    app = create_app(HttpSettings("synthetic-v1"), service_factory=lambda: service)

    async def scenario():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://test"
            ) as client:
                first = asyncio.create_task(
                    client.post(
                        "/api/v1/search/image",
                        files={"image": ("q.png", image_bytes(), "image/png")},
                    )
                )
                try:
                    assert await asyncio.to_thread(started.wait, 3)
                    first.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await first
                    assert app.state.slots.qsize() == 0
                    response = await client.post(
                        "/api/v1/search/image",
                        files={"image": ("q.png", image_bytes(), "image/png")},
                    )
                    assert response.status_code == 503
                finally:
                    release.set()
                    async with asyncio.timeout(3):
                        while app.state.slots.qsize() == 0:
                            await asyncio.sleep(0.01)
                assert (
                    await client.post(
                        "/api/v1/search/image",
                        files={"image": ("q.png", image_bytes(), "image/png")},
                    )
                ).status_code == 200

    asyncio.run(scenario())


def test_cli_is_loopback_single_worker_without_access_logs(monkeypatch):
    calls = []
    monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: calls.append((args, kwargs)))
    assert main(["--port", "8099"]) == 0
    assert calls == [
        (
            ("sahulat_api.app:create_app",),
            {
                "factory": True,
                "host": "127.0.0.1",
                "port": 8099,
                "workers": 1,
                "access_log": False,
                "proxy_headers": False,
            },
        )
    ]


@pytest.mark.parametrize("port", ["0", "65536", "-1"])
def test_invalid_cli_port(port):
    with pytest.raises(SystemExit) as error:
        main(["--port", port])
    assert error.value.code == 2
