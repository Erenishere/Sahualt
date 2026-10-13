"""Bounded multipart parsing without UploadFile's disk-spooling behavior."""

import re
from dataclasses import dataclass

from python_multipart import MultipartParser
from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import parse_options_header

from sahulat_visual.images import DEFAULT_POLICY

MIME_FORMATS = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}


class HttpFailure(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


@dataclass(frozen=True)
class ImageRequest:
    content: bytes
    mime_type: str
    top_k: int


def parse_image_request(body: bytes, content_type: str) -> ImageRequest:
    if len(content_type) > 4096:
        raise HttpFailure(400, "invalid_multipart", "Invalid multipart headers")
    media, options = parse_options_header(content_type)
    if media != b"multipart/form-data":
        raise HttpFailure(415, "unsupported_media_type", "Use multipart/form-data")
    boundary = options.get(b"boundary", b"")
    if not 1 <= len(boundary) <= 70 or any(c < 32 or c > 126 for c in boundary):
        raise HttpFailure(400, "invalid_multipart", "Invalid multipart boundary")

    values: dict[bytes, tuple[bytes, str]] = {}
    headers: dict[bytes, bytes] = {}
    header_name, header_value, data = bytearray(), bytearray(), bytearray()
    name, mime = b"", ""
    parts = 0
    ended = False

    def part_begin() -> None:
        nonlocal parts
        parts += 1
        if parts > 2:
            raise HttpFailure(422, "invalid_fields", "Only image and optional top_k are allowed")
        headers.clear()
        data.clear()

    def header_begin() -> None:
        header_name.clear()
        header_value.clear()

    def header_data(target: bytearray, chunk: bytes, start: int, end: int) -> None:
        target.extend(chunk[start:end])
        if len(header_name) + len(header_value) > 4096:
            raise HttpFailure(400, "invalid_multipart", "Multipart header is too large")

    def header_end() -> None:
        key = bytes(header_name).lower()
        if key in headers or len(headers) >= 4:
            raise HttpFailure(400, "invalid_multipart", "Invalid multipart headers")
        headers[key] = bytes(header_value)

    def headers_finished() -> None:
        nonlocal name, mime
        disposition, parameters = parse_options_header(headers.get(b"content-disposition", b""))
        name = parameters.get(b"name", b"")
        if disposition != b"form-data" or name not in {b"image", b"top_k"} or name in values:
            raise HttpFailure(422, "invalid_fields", "Only one image and one top_k are allowed")
        if b"content-transfer-encoding" in headers:
            raise HttpFailure(400, "invalid_multipart", "Transfer encoding is not supported")
        if (b"filename" in parameters) != (name == b"image"):
            raise HttpFailure(422, "invalid_fields", "image must be a file; top_k must be text")
        mime = headers.get(b"content-type", b"").decode("latin-1").lower()
        if name == b"image" and mime not in MIME_FORMATS:
            raise HttpFailure(415, "unsupported_image", "Use JPEG, PNG or WebP")

    def part_data(chunk: bytes, start: int, end: int) -> None:
        limit = DEFAULT_POLICY.max_bytes if name == b"image" else 32
        if len(data) + end - start > limit:
            if name == b"image":
                raise HttpFailure(413, "upload_too_large", "Image exceeds the byte limit")
            raise HttpFailure(422, "invalid_top_k", "top_k must be an integer from 1 to 100")
        data.extend(chunk[start:end])

    def part_end() -> None:
        values[name] = (bytes(data), mime)

    def on_end() -> None:
        nonlocal ended
        ended = True

    parser = MultipartParser(
        boundary,
        {
            "on_part_begin": part_begin,
            "on_header_begin": header_begin,
            "on_header_field": lambda c, s, e: header_data(header_name, c, s, e),
            "on_header_value": lambda c, s, e: header_data(header_value, c, s, e),
            "on_header_end": header_end,
            "on_headers_finished": headers_finished,
            "on_part_data": part_data,
            "on_part_end": part_end,
            "on_end": on_end,
        },
        max_size=len(body) + 1,
    )
    try:
        parser.write(body)
        parser.finalize()
    except (MultipartParseError, ValueError) as exc:
        raise HttpFailure(400, "invalid_multipart", "Malformed multipart request") from exc
    finally:
        parser.close()
    # The parser's finalize() does not itself reject truncated multipart messages.
    if not ended:
        raise HttpFailure(400, "invalid_multipart", "Incomplete multipart request")
    if b"image" not in values or not values[b"image"][0]:
        raise HttpFailure(422, "missing_image", "A non-empty image file is required")
    top_k_text = values.get(b"top_k", (b"5", ""))[0]
    if not re.fullmatch(rb"[0-9]{1,3}", top_k_text) or not 1 <= int(top_k_text) <= 100:
        raise HttpFailure(422, "invalid_top_k", "top_k must be an integer from 1 to 100")
    content, mime_type = values[b"image"]
    return ImageRequest(content, mime_type, int(top_k_text))
