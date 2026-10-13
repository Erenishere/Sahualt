import asyncio
import ipaddress
import math
import re
from types import TracebackType
from typing import Any

import httpx

from sahulat_visual.domain import positive_k
from sahulat_visual.images import DEFAULT_POLICY

from .errors import BridgeError
from .models import CONTRACT_VERSION, Health, Readiness, VisualSearch, parse_search, strict_json

MAX_RESPONSE_BYTES = 256 * 1024
MAX_REQUEST_BYTES = DEFAULT_POLICY.max_bytes + 64 * 1024


class VisualAIClient:
    def __init__(
        self,
        base_url: str,
        *,
        source_system: str,
        embedding_version: str,
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        try:
            url = httpx.URL(base_url)
            if url.scheme != "http" or not ipaddress.ip_address(url.host).is_loopback:
                raise ValueError
            if url.userinfo or url.query or url.fragment or url.path not in {"", "/"}:
                raise ValueError
            if not re.fullmatch(r"[a-z][a-z0-9_-]{1,63}", source_system):
                raise ValueError
            if (
                not embedding_version
                or len(embedding_version) > 512
                or not embedding_version.isascii()
                or not embedding_version.isprintable()
                or embedding_version != embedding_version.strip()
            ):
                raise ValueError
            if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
                raise ValueError
        except (ValueError, TypeError, httpx.InvalidURL):
            raise BridgeError("invalid_configuration") from None
        self.source_system, self.embedding_version = source_system, embedding_version
        self.timeout_seconds = timeout_seconds
        self._client = httpx.AsyncClient(
            base_url=url,
            transport=transport,
            timeout=timeout_seconds,
            trust_env=False,
            follow_redirects=False,
            headers={"Accept": "application/json", "Accept-Encoding": "identity"},
            limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
        )

    async def __aenter__(self) -> "VisualAIClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            # The overall deadline also covers slow/dribbling responses and test transports.
            async with asyncio.timeout(self.timeout_seconds):
                async with self._client.stream(method, path, **kwargs) as response:
                    media = response.headers.get("content-type", "").split(";", 1)[0].lower()
                    if (
                        media != "application/json"
                        or response.headers.get("content-encoding", "identity") != "identity"
                    ):
                        raise BridgeError("malformed_response")
                    body = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                        if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                            raise BridgeError("malformed_response")
                        body.extend(chunk)
                    payload = strict_json(bytes(body))
                    if response.status_code != 200:
                        self._raise_upstream_error(response.status_code, payload, path)
                    return payload
        except (TimeoutError, httpx.TimeoutException):
            raise BridgeError("api_timeout") from None
        except httpx.RequestError:
            raise BridgeError("api_unavailable") from None

    @staticmethod
    def _raise_upstream_error(status: int, payload: dict[str, Any], path: str) -> None:
        error = payload.get("error")
        if (
            set(payload) != {"error"}
            or not isinstance(error, dict)
            or set(error) != {"code", "message"}
        ):
            raise BridgeError("malformed_response")
        if not isinstance(error["code"], str) or not isinstance(error["message"], str):
            raise BridgeError("malformed_response")
        if status == 503:
            if error["code"] == "visual_busy":
                raise BridgeError("api_busy")
            if error["code"] == "visual_unavailable":
                raise BridgeError(
                    "model_not_ready" if path == "/health/ready" else "api_unavailable"
                )
        mapping = {
            400: "image_request_rejected",
            408: "api_timeout",
            413: "upload_too_large",
            415: "unsupported_image",
            422: "image_request_rejected",
            500: "api_failure",
        }
        raise BridgeError(mapping.get(status, "malformed_response"))

    async def health(self) -> Health:
        if await self._request("GET", "/health/live") != {"status": "live"}:
            raise BridgeError("malformed_response")
        return Health()

    async def readiness(self) -> Readiness:
        if await self._request("GET", "/health/ready") != {
            "status": "ready",
            "contract_version": CONTRACT_VERSION,
        }:
            raise BridgeError("contract_mismatch")
        return Readiness()

    async def search(self, image: bytes, *, mime_type: str, top_k: int = 5) -> VisualSearch:
        try:
            positive_k(top_k)
            if top_k > 100:
                raise ValueError
        except ValueError:
            raise BridgeError("invalid_top_k") from None
        if not isinstance(image, bytes) or not image:
            raise BridgeError("invalid_image")
        if len(image) > DEFAULT_POLICY.max_bytes:
            raise BridgeError("upload_too_large")
        if mime_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise BridgeError("unsupported_image")
        request = self._client.build_request(
            "POST",
            "/api/v1/search/image",
            files={"image": ("query", image, mime_type)},
            data={"top_k": str(top_k)},
        )
        if int(request.headers["content-length"]) > MAX_REQUEST_BYTES:
            raise BridgeError("upload_too_large")
        payload = await self._request(
            "POST",
            "/api/v1/search/image",
            files={"image": ("query", image, mime_type)},
            data={"top_k": str(top_k)},
        )
        return parse_search(
            payload,
            source_system=self.source_system,
            embedding_version=self.embedding_version,
            top_k=top_k,
        )
