import asyncio
from copy import deepcopy

import httpx
import pytest

from integration.visual_bridge_v1.client import MAX_RESPONSE_BYTES, VisualAIClient
from integration.visual_bridge_v1.errors import BridgeError
from integration.visual_bridge_v1.models import CONTRACT_VERSION
from sahulat_visual.images import DEFAULT_POLICY

pytestmark = pytest.mark.unit


def search_payload():
    return {
        "contract_version": CONTRACT_VERSION,
        "identity_scope": "external",
        "source_system": "synthetic-v1",
        "model": "openclip",
        "embedding_version": "synthetic-openclip-v1",
        "results": [
            {"product_id": "A", "matched_image_id": "A/image_1.png", "score": 0.9},
            {"product_id": "B", "matched_image_id": "B/image_1.png", "score": 0.6},
        ],
    }


def client(transport, **kwargs):
    return VisualAIClient(
        "http://127.0.0.1:8000",
        source_system="synthetic-v1",
        embedding_version="synthetic-openclip-v1",
        transport=transport,
        **kwargs,
    )


@pytest.mark.parametrize("version", ["", " leading", "trailing ", "bad\nversion", "\u2603"])
def test_invalid_expected_model_identity_is_rejected_before_transport(version):
    with pytest.raises(BridgeError, match="invalid_configuration"):
        VisualAIClient(
            "http://127.0.0.1:8000",
            source_system="synthetic-v1",
            embedding_version=version,
        )


def test_health_readiness_and_typed_search():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/health/live":
            return httpx.Response(200, json={"status": "live"})
        if request.url.path == "/health/ready":
            return httpx.Response(
                200, json={"status": "ready", "contract_version": CONTRACT_VERSION}
            )
        assert b"original-image-bytes" in request.content
        return httpx.Response(200, json=search_payload())

    async def scenario():
        async with client(httpx.MockTransport(handler)) as api:
            assert (await api.health()).status == "live"
            assert (await api.readiness()).status == "ready"
            result = await api.search(b"original-image-bytes", mime_type="image/png")
            assert [m.rank for m in result.matches] == [1, 2]
            assert [m.score for m in result.matches] == [0.9, 0.6]
            assert [m.external_product_id for m in result.matches] == ["A", "B"]

    asyncio.run(scenario())
    assert [r.url.path for r in requests] == [
        "/health/live",
        "/health/ready",
        "/api/v1/search/image",
    ]


@pytest.mark.parametrize(
    "status,code,expected",
    [
        (400, "invalid_image", "image_request_rejected"),
        (413, "upload_too_large", "upload_too_large"),
        (415, "unsupported_image", "unsupported_image"),
        (408, "upload_timeout", "api_timeout"),
        (422, "invalid_fields", "image_request_rejected"),
        (503, "visual_unavailable", "api_unavailable"),
        (503, "visual_busy", "api_busy"),
        (500, "visual_error", "api_failure"),
    ],
)
def test_safe_error_mapping(status, code, expected):
    async def scenario():
        async with client(
            httpx.MockTransport(
                lambda r: httpx.Response(
                    status,
                    json={"error": {"code": code, "message": "SECRET C:/private/db/password"}},
                )
            )
        ) as api:
            with pytest.raises(BridgeError) as error:
                await api.search(b"image", mime_type="image/png")
            assert error.value.code == expected and str(error.value) == expected
            assert error.value.__suppress_context__ or "SECRET" not in repr(error.value)

    asyncio.run(scenario())


def test_model_not_ready():
    async def scenario():
        async with client(
            httpx.MockTransport(
                lambda r: httpx.Response(
                    503, json={"error": {"code": "visual_unavailable", "message": "private"}}
                )
            )
        ) as api:
            with pytest.raises(BridgeError, match="model_not_ready"):
                await api.readiness()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "failure,expected",
    [(httpx.ConnectError, "api_unavailable"), (httpx.ReadTimeout, "api_timeout")],
)
def test_transport_failures(failure, expected):
    def handler(request):
        raise failure("SECRET", request=request)

    async def scenario():
        async with client(httpx.MockTransport(handler)) as api:
            with pytest.raises(BridgeError, match=expected) as error:
                await api.health()
            assert error.value.__suppress_context__

    asyncio.run(scenario())


def test_overall_timeout():
    async def handler(request):
        await asyncio.sleep(0.05)
        return httpx.Response(200, json={"status": "live"})

    async def scenario():
        async with client(httpx.MockTransport(handler), timeout_seconds=0.01) as api:
            with pytest.raises(BridgeError, match="api_timeout"):
                await api.health()

    asyncio.run(scenario())


def test_cancellation_propagates_and_closes_response():
    started, stopped = asyncio.Event(), asyncio.Event()

    async def handler(request):
        started.set()
        try:
            await asyncio.sleep(10)
        finally:
            stopped.set()

    async def scenario():
        async with client(httpx.MockTransport(handler)) as api:
            task = asyncio.create_task(api.health())
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert stopped.is_set()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "body", [b"broken", b"[]", b"\xff", b'{"results":NaN}', b'{"status":"live","status":"live"}']
)
def test_malformed_json(body):
    async def scenario():
        async with client(
            httpx.MockTransport(
                lambda r: httpx.Response(
                    200, content=body, headers={"content-type": "application/json"}
                )
            )
        ) as api:
            with pytest.raises(BridgeError, match="malformed_response"):
                await api.health()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "fault,expected",
    [
        ("extra", "malformed_response"),
        ("missing", "malformed_response"),
        ("version", "contract_mismatch"),
        ("canonical", "contract_mismatch"),
        ("namespace", "scope_mismatch"),
        ("model", "model_identity_mismatch"),
        ("embedding", "model_identity_mismatch"),
        ("score_bool", "malformed_response"),
        ("score_bigint", "malformed_response"),
        ("score_string", "malformed_response"),
        ("duplicates", "ambiguous_identity"),
        ("image_duplicate", "ambiguous_identity"),
        ("ranking", "ranking_violation"),
        ("tie_order", "ranking_violation"),
        ("path", "malformed_response"),
        ("bad_id", "invalid_identity"),
        ("too_many", "malformed_response"),
        ("null_results", "malformed_response"),
    ],
)
def test_strict_search_contract(fault, expected):
    payload = deepcopy(search_payload())
    if fault == "extra":
        payload["price"] = 1
    elif fault == "missing":
        del payload["source_system"]
    elif fault == "version":
        payload["contract_version"] = "visual-http-v2"
    elif fault == "canonical":
        payload["identity_scope"] = "canonical"
    elif fault == "namespace":
        payload["source_system"] = "wrong-v1"
    elif fault == "model":
        payload["model"] = "fashionclip"
    elif fault == "embedding":
        payload["embedding_version"] = "unknown"
    elif fault == "score_bool":
        payload["results"][0]["score"] = True
    elif fault == "score_bigint":
        payload["results"][0]["score"] = 10**500
    elif fault == "score_string":
        payload["results"][0]["score"] = "0.9"
    elif fault == "duplicates":
        payload["results"][1]["product_id"] = "A"
    elif fault == "image_duplicate":
        payload["results"][1]["matched_image_id"] = payload["results"][0]["matched_image_id"]
    elif fault == "ranking":
        payload["results"].reverse()
    elif fault == "tie_order":
        payload["results"][1]["score"] = 0.9
        payload["results"].reverse()
    elif fault == "path":
        payload["results"][0]["matched_image_path"] = "private"
    elif fault == "bad_id":
        payload["results"][0]["product_id"] = "../bad"
    elif fault == "too_many":
        payload["results"] *= 3
    else:
        payload["results"] = None

    async def scenario():
        async with client(httpx.MockTransport(lambda r: httpx.Response(200, json=payload))) as api:
            with pytest.raises(BridgeError, match=expected):
                await api.search(b"image", mime_type="image/png")

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "value",
    [
        "http://example.com",
        "http://localhost:8000",
        "http://127.0.0.1:8000/path",
        "http://u:p@127.0.0.1",
        "http://127.0.0.1?q=1",
        "https://127.0.0.1",
        "http://127.0.0.1#fragment",
    ],
)
def test_non_loopback_or_ambiguous_configuration_rejected(value):
    with pytest.raises(BridgeError, match="invalid_configuration"):
        VisualAIClient(value, source_system="synthetic-v1", embedding_version="synthetic")


@pytest.mark.parametrize(
    "image,mime,top_k,expected",
    [
        (b"", "image/png", 1, "invalid_image"),
        (b"image", "image/svg+xml", 1, "unsupported_image"),
        (b"image", "image/png", True, "invalid_top_k"),
        (b"image", "image/png", 101, "invalid_top_k"),
        (b"oversized", "image/png", 1, "upload_too_large"),
    ],
)
def test_invalid_upload_never_calls_api(image, mime, top_k, expected):
    if image == b"oversized":
        image = b"x" * (DEFAULT_POLICY.max_bytes + 1)

    def forbidden(request):
        pytest.fail("Invalid input reached HTTP transport")

    async def scenario():
        async with client(httpx.MockTransport(forbidden)) as api:
            with pytest.raises(BridgeError, match=expected):
                await api.search(image, mime_type=mime, top_k=top_k)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "mode", ["content_type", "compression", "oversized", "redirect", "bad_error"]
)
def test_untrusted_responses_fail_closed(mode):
    def handler(request):
        if mode == "content_type":
            return httpx.Response(200, json={}, headers={"content-type": "text/html"})
        if mode == "compression":
            return httpx.Response(
                200,
                content=b"x",
                headers={"content-type": "application/json", "content-encoding": "gzip"},
            )
        if mode == "oversized":
            return httpx.Response(
                200,
                content=b"x" * (MAX_RESPONSE_BYTES + 1),
                headers={"content-type": "application/json"},
            )
        if mode == "redirect":
            return httpx.Response(302, json={}, headers={"location": "http://example.com"})
        return httpx.Response(503, json={"error": "bad"})

    async def scenario():
        async with client(httpx.MockTransport(handler)) as api:
            with pytest.raises(BridgeError, match="malformed_response"):
                await api.health()

    asyncio.run(scenario())
