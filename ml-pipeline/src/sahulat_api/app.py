import asyncio
import hashlib
import io
import logging
import warnings
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, Request
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.requests import ClientDisconnect
from starlette.responses import JSONResponse

from sahulat_visual.config import Settings
from sahulat_visual.errors import EmptyIndexError, IndexCompatibilityError, InvalidImageError
from sahulat_visual.images import DEFAULT_POLICY
from sahulat_visual.index import InMemoryVectorIndex
from sahulat_visual.retrieval import VisualRetrievalService

from .settings import HttpSettings
from .uploads import MIME_FORMATS, HttpFailure, ImageRequest, parse_image_request

CONTRACT_VERSION = "visual-http-v1"
logger = logging.getLogger(__name__)


class ImageResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    product_id: str
    score: float
    matched_image_id: str


class ImageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    contract_version: Literal["visual-http-v1"] = "visual-http-v1"
    identity_scope: Literal["external"] = "external"
    source_system: str
    model: str
    embedding_version: str
    results: list[ImageResult]


class ErrorDetails(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    code: str
    message: str


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    error: ErrorDetails


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status: {"model": ErrorResponse, "description": description}
    for status, description in [
        (400, "Malformed multipart/image or invalid declared length"),
        (408, "Upload timeout or disconnect"),
        (413, "Request/image byte limit exceeded"),
        (415, "Unsupported request encoding/media or mismatched decoded image format"),
        (422, "Missing, duplicate, unknown or invalid multipart fields"),
        (500, "Unexpected visual service failure"),
        (503, "Visual service unavailable or busy"),
    ]
}


def load_visual_service(settings: HttpSettings) -> VisualRetrievalService:
    """Load only pinned existing assets; no index creation or DB configuration."""
    if settings.index_path is None:
        raise ValueError("AI_VISUAL_INDEX_PATH is required")
    with settings.index_path.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    if checksum != settings.index_sha256:
        raise IndexCompatibilityError("Visual index checksum mismatch")
    index = InMemoryVectorIndex.load(settings.index_path)
    if not index.count or index.metadata.get("dataset_version") != settings.source_system:
        raise IndexCompatibilityError("Empty index or source namespace mismatch")
    # Existing pinned adapters honor HF_HUB_OFFLINE. Do not change Visual V1 itself.
    import os

    if os.getenv("HF_HUB_OFFLINE") != "1":
        raise ValueError("HF_HUB_OFFLINE=1 is required; provision model assets offline")
    from sahulat_visual.encoders.factory import create_encoder

    visual = Settings.from_env()
    return VisualRetrievalService(create_encoder(visual), index, visual.image_top_k)


def search_image(service: VisualRetrievalService, query: ImageRequest) -> list[ImageResult]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(query.content)) as image:
                if image.format != MIME_FORMATS[query.mime_type]:
                    raise HttpFailure(
                        415, "unsupported_image", "Image format must match its MIME type"
                    )
    except (
        OSError,
        ValueError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise HttpFailure(400, "invalid_image", "Image cannot be decoded safely") from exc
    return [
        ImageResult(product_id=m.product_id, score=m.score, matched_image_id=m.matched_image_id)
        for m in service.search(query.content, query.top_k)
    ]


def process_image_request(
    service: VisualRetrievalService, body: bytes, content_type: str
) -> list[ImageResult]:
    return search_image(service, parse_image_request(body, content_type))


def create_app(
    settings: HttpSettings | None = None,
    *,
    service_factory: Callable[[], VisualRetrievalService] | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.service = None
        app.state.settings = None
        try:
            active = settings or HttpSettings.from_env()
            app.state.settings = active
            service = await run_in_threadpool(
                service_factory or (lambda: load_visual_service(active))
            )
            if service.encoder.identity != service.index.identity or not service.index.count:
                raise IndexCompatibilityError("Empty/incompatible visual service")
            index = service.index
            if (
                not isinstance(index, InMemoryVectorIndex)
                or index.metadata.get("dataset_version") != active.source_system
            ):
                raise IndexCompatibilityError("Index namespace differs from HTTP namespace")
            if service.policy != DEFAULT_POLICY:
                raise IndexCompatibilityError("HTTP V1 requires the locked image policy")
            app.state.slots = asyncio.Queue[None](active.max_concurrent_requests)
            for _ in range(active.max_concurrent_requests):
                app.state.slots.put_nowait(None)
            app.state.service = service
        except Exception as exc:
            # Error text/tracebacks may contain machine paths or configuration secrets.
            logger.error("visual_startup_failed", extra={"error_type": type(exc).__name__})
        try:
            yield
        finally:
            app.state.service = None
            app.state.settings = None

    app = FastAPI(
        title="Sahulat AI Visual Runtime",
        version=CONTRACT_VERSION,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )
    # Unstarted apps fail closed too; lifespan initialization is mandatory.
    app.state.service = None

    @app.exception_handler(HttpFailure)
    async def expected_error(request: Request, exc: HttpFailure) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": exc.code, "message": exc.message}},
            status_code=exc.status,
            headers={"Cache-Control": "no-store"},
        )

    @app.exception_handler(HTTPException)
    async def routing_error(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": "http_error", "message": "Request cannot be handled"}},
            status_code=exc.status_code,
        )

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/health/ready", responses={503: ERROR_RESPONSES[503]})
    async def ready() -> dict[str, str]:
        if app.state.service is None:
            raise HttpFailure(503, "visual_unavailable", "Visual service is not ready")
        return {"status": "ready", "contract_version": CONTRACT_VERSION}

    @app.post(
        "/api/v1/search/image",
        response_model=ImageResponse,
        responses=ERROR_RESPONSES,
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "multipart/form-data": {
                        "schema": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["image"],
                            "properties": {
                                "image": {"type": "string", "format": "binary"},
                                "top_k": {
                                    "type": "integer",
                                    "minimum": 1,
                                    "maximum": 100,
                                    "default": 5,
                                },
                            },
                        }
                    }
                },
            }
        },
    )
    async def query_image(request: Request) -> JSONResponse:
        service: VisualRetrievalService | None = app.state.service
        if service is None:
            raise HttpFailure(503, "visual_unavailable", "Visual service is not ready")
        active: HttpSettings = app.state.settings
        slots: asyncio.Queue[None] = app.state.slots
        try:
            slots.get_nowait()
        except asyncio.QueueEmpty as exc:
            raise HttpFailure(503, "visual_busy", "Visual service is busy; retry later") from exc
        release_slot = True
        try:
            if request.headers.get("content-encoding", "identity") != "identity":
                raise HttpFailure(
                    415, "unsupported_encoding", "Compressed requests are not supported"
                )
            if request.url.query:
                raise HttpFailure(422, "invalid_fields", "Supply top_k in the multipart body")
            declared = request.headers.get("content-length")
            if declared is not None:
                if not re_decimal(declared):
                    raise HttpFailure(400, "invalid_length", "Invalid Content-Length")
                if int(declared) > active.max_request_bytes:
                    raise HttpFailure(413, "upload_too_large", "Request exceeds the byte limit")
            content_type = request.headers.get("content-type", "")
            if not content_type.lower().startswith("multipart/form-data;"):
                raise HttpFailure(415, "unsupported_media_type", "Use multipart/form-data")
            body = bytearray()
            async with asyncio.timeout(active.body_timeout_seconds):
                async for chunk in request.stream():
                    if len(body) + len(chunk) > active.max_request_bytes:
                        raise HttpFailure(413, "upload_too_large", "Request exceeds the byte limit")
                    body.extend(chunk)
            if declared is not None and len(body) != int(declared):
                raise HttpFailure(
                    400, "invalid_length", "Content-Length does not match request bytes"
                )
            job = asyncio.create_task(
                run_in_threadpool(process_image_request, service, bytes(body), content_type)
            )
            del body
            try:
                results = await asyncio.shield(job)
            except asyncio.CancelledError:
                # A cancelled HTTP task cannot stop synchronous model execution. Keep its
                # admission slot until the worker really finishes, even on repeated cancel.
                release_slot = False

                def release_after_work(done: asyncio.Task[list[ImageResult]]) -> None:
                    if not done.cancelled():
                        failure = done.exception()
                        if isinstance(failure, (EmptyIndexError, IndexCompatibilityError)):
                            app.state.service = None
                    slots.put_nowait(None)

                job.add_done_callback(release_after_work)
                raise
            payload = ImageResponse(
                source_system=active.source_system,
                model=service.encoder.model_name,
                embedding_version=service.index.identity.embedding_version,
                results=results,
            )
            return JSONResponse(payload.model_dump(), headers={"Cache-Control": "no-store"})
        except HttpFailure:
            raise
        except (TimeoutError, ClientDisconnect) as exc:
            raise HttpFailure(408, "upload_timeout", "Upload did not complete") from exc
        except InvalidImageError as exc:
            raise HttpFailure(400, "invalid_image", "Image cannot be decoded safely") from exc
        except (EmptyIndexError, IndexCompatibilityError) as exc:
            app.state.service = None
            raise HttpFailure(503, "visual_unavailable", "Visual service is not ready") from exc
        except Exception as exc:
            logger.error("visual_request_failed", extra={"error_type": type(exc).__name__})
            raise HttpFailure(500, "visual_error", "Visual request failed") from exc
        finally:
            if release_slot:
                slots.put_nowait(None)

    return app


def re_decimal(value: str) -> bool:
    return 1 <= len(value) <= 20 and value.isascii() and value.isdecimal()
