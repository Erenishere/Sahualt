import asyncio
import io
import threading
from dataclasses import replace

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from sahulat_api.app import create_app, load_visual_service
from sahulat_api.settings import HttpSettings
from sahulat_api.uploads import HttpFailure, parse_image_request
from sahulat_visual.domain import ImageRecord
from sahulat_visual.errors import IndexCompatibilityError, ModelLoadError
from sahulat_visual.images import ImagePolicy
from sahulat_visual.index import InMemoryVectorIndex
from sahulat_visual.retrieval import VisualRetrievalService

pytestmark = pytest.mark.unit


def image_bytes(format="PNG", size=(32, 32)):
    stream = io.BytesIO()
    Image.new("RGB", size, (255, 0, 0)).save(stream, format=format)
    return stream.getvalue()


@pytest.fixture
def service(encoder):
    # Duplicate views/tied similarities exercise real MAX aggregation, not a ranking stub.
    records = [
        ImageRecord("b1", "B", "C:/private/source/b1.png"),
        ImageRecord("a2", "A", "C:/private/source/a2.png"),
        ImageRecord("a1", "A", "C:/private/source/a1.png"),
    ]
    index = InMemoryVectorIndex(
        encoder.identity,
        np.array([[1, 0, 0]] * 3),
        records,
        {"dataset_version": "synthetic-v1"},
    )
    return VisualRetrievalService(encoder, index, image_top_k=1)


@pytest.fixture
def app(service):
    return create_app(HttpSettings("synthetic-v1"), service_factory=lambda: service)


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


def post_image(client, content=None, mime="image/png", data=None, **kwargs):
    return client.post(
        "/api/v1/search/image",
        files={"image": ("../../private.png", image_bytes() if content is None else content, mime)},
        data=data,
        **kwargs,
    )


def test_success_preserves_ranking_and_namespaced_safe_dto(client):
    response = post_image(client)
    assert response.status_code == 200
    assert response.json() == {
        "contract_version": "visual-http-v1",
        "identity_scope": "external",
        "source_system": "synthetic-v1",
        "model": "fixture",
        "embedding_version": "fixture-v1",
        "results": [
            {"product_id": "A", "matched_image_id": "a1", "score": 1.0},
            {"product_id": "B", "matched_image_id": "b1", "score": 1.0},
        ],
    }
    assert response.headers["cache-control"] == "no-store"
    assert "private" not in response.text and "path" not in response.text


@pytest.mark.parametrize("top_k", ["1", "100"])
def test_top_k_valid(client, top_k):
    response = post_image(client, data={"top_k": top_k})
    assert response.status_code == 200
    assert len(response.json()["results"]) == min(int(top_k), 2)


@pytest.mark.parametrize("top_k", ["0", "-1", "101", "true", "1.0", " 1", "", "١", "9" * 40])
def test_top_k_invalid(client, top_k):
    response = post_image(client, data={"top_k": top_k})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_top_k"


def test_health(client):
    assert client.get("/health/live").json() == {"status": "live"}
    assert client.get("/health/ready").json()["status"] == "ready"


def test_load_once_and_release_on_shutdown(service):
    calls = []

    def factory():
        calls.append(1)
        return service

    app = create_app(HttpSettings("synthetic-v1"), service_factory=factory)
    assert calls == []
    with TestClient(app) as client:
        assert post_image(client).status_code == 200
        assert post_image(client).status_code == 200
        assert calls == [1] and app.state.service is service
    assert app.state.service is None


@pytest.mark.parametrize("failure", [ModelLoadError, IndexCompatibilityError, OSError])
def test_startup_failure_is_not_ready_and_does_not_leak(failure, caplog):
    def factory():
        raise failure("C:/secret/path password=DO_NOT_EXPOSE")

    with TestClient(create_app(HttpSettings("synthetic-v1"), service_factory=factory)) as client:
        assert client.get("/health/live").status_code == 200
        for response in (client.get("/health/ready"), post_image(client)):
            assert response.status_code == 503 and "secret" not in response.text
    assert "DO_NOT_EXPOSE" not in caplog.text


@pytest.mark.parametrize("fault", ["empty", "namespace", "identity"])
def test_invalid_injected_service_fails_readiness(service, fault):
    if fault == "empty":
        service.index = InMemoryVectorIndex(service.encoder.identity, np.empty((0, 3)), [])
    elif fault == "namespace":
        service.index.metadata["dataset_version"] = "wrong-v1"
    else:
        service.index.identity = replace(service.encoder.identity, embedding_version="different")
    with TestClient(
        create_app(HttpSettings("synthetic-v1"), service_factory=lambda: service)
    ) as client:
        assert client.get("/health/ready").status_code == 503


def test_missing_runtime_environment_fails_closed(monkeypatch):
    monkeypatch.delenv("AI_VISUAL_SOURCE_SYSTEM", raising=False)
    with TestClient(create_app()) as client:
        assert client.get("/health/live").status_code == 200
        assert post_image(client).status_code == 503


def test_no_lifespan_fails_closed(app):
    assert post_image(TestClient(app)).status_code == 503


@pytest.mark.parametrize("body", [b"garbage", image_bytes(size=(1, 1))])
def test_bad_image(client, body):
    assert post_image(client, body).status_code == 400


@pytest.mark.parametrize(
    "body,mime",
    [
        (image_bytes(), "image/jpeg"),
        (image_bytes("GIF"), "image/png"),
        (b"<svg/>", "image/svg+xml"),
    ],
)
def test_unsupported_or_mismatched_format(client, body, mime):
    assert post_image(client, body, mime).status_code == 415


@pytest.mark.parametrize("format,mime", [("JPEG", "image/jpeg"), ("WEBP", "image/webp")])
def test_other_supported_formats(client, format, mime):
    assert post_image(client, image_bytes(format), mime).status_code == 200


def test_missing_and_empty_file(client):
    assert post_image(client, b"").status_code == 422
    assert client.post("/api/v1/search/image", files={"top_k": (None, "1")}).status_code == 422


@pytest.mark.parametrize(
    "fields",
    [
        [
            ("image", ("q.png", image_bytes(), "image/png")),
            ("image", ("q2.png", image_bytes(), "image/png")),
        ],
        [
            ("image", ("q.png", image_bytes(), "image/png")),
            ("top_k", (None, "1")),
            ("top_k", (None, "2")),
        ],
        [("image", ("q.png", image_bytes(), "image/png")), ("query_text", (None, "forbidden"))],
        [("image", (None, "not-a-file"))],
        [("image", ("q.png", image_bytes(), "image/png")), ("top_k", ("k.txt", "1"))],
    ],
)
def test_duplicate_unknown_and_wrongly_typed_parts(client, fields):
    assert client.post("/api/v1/search/image", files=fields).status_code == 422


def test_truncated_multipart_rejected(client):
    request = httpx.Request(
        "POST",
        "http://test/api/v1/search/image",
        files={"image": ("q.png", image_bytes(), "image/png")},
    )
    response = client.post(
        "/api/v1/search/image",
        content=request.read()[:-6],
        headers={"content-type": request.headers["content-type"]},
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    "content_type", ["multipart/form-data; boundary=", "multipart/form-data; boundary=" + "a" * 71]
)
def test_malformed_multipart(client, content_type):
    assert (
        client.post(
            "/api/v1/search/image", content=b"broken", headers={"content-type": content_type}
        ).status_code
        == 400
    )


def test_compressed_nonmultipart_and_url_parameters_rejected(client):
    assert post_image(client, headers={"content-encoding": "gzip"}).status_code == 415
    assert client.post("/api/v1/search/image", json={"image": "no"}).status_code == 415
    assert post_image(client, params={"top_k": "1"}).status_code == 422


def test_content_length_validation(client):
    assert post_image(client, headers={"content-length": "999999999"}).status_code == 413
    assert post_image(client, headers={"content-length": "nonsense"}).status_code == 400
    assert post_image(client, headers={"content-length": "1"}).status_code == 400


def test_chunked_body_bound_without_content_length(service):
    app = create_app(
        HttpSettings("synthetic-v1", max_request_bytes=100), service_factory=lambda: service
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/search/image",
            content=iter([b"a" * 60, b"b" * 60]),
            headers={"content-type": "multipart/form-data; boundary=x"},
        )
        assert response.status_code == 413


def test_unexpected_failure_safe_and_slot_reusable(client, service, monkeypatch, caplog):
    original = service.search

    def fail(*args, **kwargs):
        raise RuntimeError("C:/private/API_SECRET")

    monkeypatch.setattr(service, "search", fail)
    response = post_image(client)
    assert response.status_code == 500
    assert "API_SECRET" not in response.text and "API_SECRET" not in caplog.text
    monkeypatch.setattr(service, "search", original)
    assert post_image(client).status_code == 200


def test_runtime_identity_fault_removes_readiness(client, service, monkeypatch):
    def fail(*args, **kwargs):
        raise IndexCompatibilityError("private details")

    monkeypatch.setattr(service, "search", fail)
    assert post_image(client).status_code == 503
    assert client.get("/health/ready").status_code == 503


def test_overload_is_bounded_and_health_remains_responsive(service, monkeypatch):
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
                    assert (await client.get("/health/live")).status_code == 200
                    second = await client.post(
                        "/api/v1/search/image",
                        files={"image": ("q.png", image_bytes(), "image/png")},
                    )
                    assert second.status_code == 503
                    assert second.json()["error"]["code"] == "visual_busy"
                finally:
                    release.set()
                    assert (await first).status_code == 200

    asyncio.run(scenario())


def test_upload_timeout_and_slot_release(service):
    app = create_app(
        HttpSettings("synthetic-v1", body_timeout_seconds=0.01), service_factory=lambda: service
    )

    async def scenario():
        async def slow():
            yield b"x"
            await asyncio.sleep(0.05)
            yield b"y"

        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/v1/search/image",
                    content=slow(),
                    headers={"content-type": "multipart/form-data; boundary=x"},
                )
                assert response.status_code == 408
                assert (
                    await client.post(
                        "/api/v1/search/image",
                        files={"image": ("q.png", image_bytes(), "image/png")},
                    )
                ).status_code == 200

    asyncio.run(scenario())


def test_parser_cannot_spool_or_persist_uploads(client, monkeypatch):
    import tempfile

    def forbidden(*args, **kwargs):
        pytest.fail("Upload attempted filesystem persistence")

    monkeypatch.setattr(tempfile, "TemporaryFile", forbidden)
    monkeypatch.setattr(tempfile, "NamedTemporaryFile", forbidden)
    # >1 MiB would spool with default UploadFile handling; synthetic only.
    assert post_image(client, image_bytes() + b"\0" * (1024 * 1024)).status_code == 200


def test_image_byte_limit(client):
    assert post_image(client, b"x" * (ImagePolicy().max_bytes + 1)).status_code == 413


def test_decompression_bomb_is_a_safe_client_failure(client, monkeypatch):
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 10)
    assert post_image(client).status_code == 400


def test_openapi_contract_and_forbidden_routes(client):
    schema = client.get("/openapi.json").json()
    assert set(schema["paths"]) == {"/health/live", "/health/ready", "/api/v1/search/image"}
    spec = schema["paths"]["/api/v1/search/image"]["post"]["requestBody"]["content"][
        "multipart/form-data"
    ]["schema"]
    assert spec["required"] == ["image"] and spec["additionalProperties"] is False
    assert set(spec["properties"]) == {"image", "top_k"}
    for route in ["/api/v1/search/text", "/api/v1/search/voice", "/docs", "/products"]:
        assert client.get(route).status_code == 404


def test_loader_missing_and_drifted_assets(tmp_path):
    with pytest.raises(ValueError):
        load_visual_service(HttpSettings("synthetic-v1"))
    path = tmp_path / "index.npz"
    path.write_bytes(b"not an index")
    with pytest.raises(IndexCompatibilityError):
        load_visual_service(HttpSettings("synthetic-v1", index_path=path, index_sha256="0" * 64))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"source_system": ""},
        {"source_system": "../bad"},
        {"max_concurrent_requests": 0},
        {"max_concurrent_requests": True},
        {"body_timeout_seconds": 0},
        {"body_timeout_seconds": float("nan")},
        {"max_request_bytes": 0},
        {"index_path": "index.npz"},
    ],
)
def test_invalid_settings(kwargs):
    with pytest.raises(ValueError):
        HttpSettings(**({"source_system": "synthetic-v1"} | kwargs))


def test_header_limits_and_transfer_encoding():
    for body in [
        b'--x\r\nContent-Disposition: form-data; name="image"; filename="q.png"\r\n'
        b"Content-Type: image/png\r\nContent-Transfer-Encoding: base64\r\n\r\nx\r\n--x--\r\n",
        b'--x\r\nContent-Disposition: form-data; name="image"; filename="'
        + b"a" * 5000
        + b'"\r\n\r\nx\r\n--x--\r\n',
    ]:
        with pytest.raises(HttpFailure) as failure:
            parse_image_request(body, "multipart/form-data; boundary=x")
        assert failure.value.status == 400
