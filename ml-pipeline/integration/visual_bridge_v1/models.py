import json
import math
import unicodedata
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from .errors import BridgeError

CONTRACT_VERSION = "visual-http-v1"


def external_id(value: object) -> str:
    # IDs are opaque, not file references. Khaadi image IDs legitimately contain '/'.
    if not isinstance(value, str) or not 0 < len(value) <= 512 or value != value.strip():
        raise BridgeError("invalid_identity")
    if any(unicodedata.category(c).startswith("C") for c in value):
        raise BridgeError("invalid_identity")
    if value.startswith(("/", "\\")) or "\\" in value or ":" in value:
        raise BridgeError("invalid_identity")
    if any(part in {"", ".", ".."} for part in value.split("/")):
        raise BridgeError("invalid_identity")
    return value


def strict_json(content: bytes) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    def nonfinite(value: str) -> None:
        raise ValueError("nonfinite JSON")

    try:
        result = json.loads(
            content.decode("utf-8"), object_pairs_hook=pairs, parse_constant=nonfinite
        )
        if not isinstance(result, dict):
            raise ValueError("expected object")
        return result
    except (ValueError, UnicodeError, RecursionError):
        raise BridgeError("malformed_response") from None


@dataclass(frozen=True)
class Health:
    status: str = "live"


@dataclass(frozen=True)
class Readiness:
    status: str = "ready"
    contract_version: str = CONTRACT_VERSION


@dataclass(frozen=True)
class RankedVisualMatch:
    rank: int
    external_product_id: str
    external_image_id: str
    score: float


@dataclass(frozen=True)
class VisualSearch:
    source_system: str
    model: str
    embedding_version: str
    matches: tuple[RankedVisualMatch, ...]


@dataclass(frozen=True)
class VerifiedProduct:
    product_id: UUID
    name: str
    description: str


@dataclass(frozen=True)
class ResolvedVisualMatch:
    rank: int
    score: float
    external_product_id: str
    external_image_id: str
    canonical_image_id: UUID
    product: VerifiedProduct


def parse_search(
    payload: dict[str, Any], *, source_system: str, embedding_version: str, top_k: int
) -> VisualSearch:
    if set(payload) != {
        "contract_version",
        "identity_scope",
        "source_system",
        "model",
        "embedding_version",
        "results",
    }:
        raise BridgeError("malformed_response")
    if payload["contract_version"] != CONTRACT_VERSION or payload["identity_scope"] != "external":
        raise BridgeError("contract_mismatch")
    if payload["source_system"] != source_system:
        raise BridgeError("scope_mismatch")
    if payload["model"] != "openclip" or payload["embedding_version"] != embedding_version:
        raise BridgeError("model_identity_mismatch")
    results = payload["results"]
    if not isinstance(results, list) or len(results) > top_k:
        raise BridgeError("malformed_response")
    matches = []
    products: set[str] = set()
    images: set[str] = set()
    previous: tuple[float, str] | None = None
    for rank, value in enumerate(results, 1):
        if not isinstance(value, dict) or set(value) != {"product_id", "score", "matched_image_id"}:
            raise BridgeError("malformed_response")
        product, image = external_id(value["product_id"]), external_id(value["matched_image_id"])
        score = value["score"]
        if type(score) not in (float, int) or not -1 <= score <= 1 or not math.isfinite(score):
            raise BridgeError("malformed_response")
        if product in products or image in images:
            raise BridgeError("ambiguous_identity")
        # Check the frozen ordering; never repair it by sorting at the consumer.
        key = (-float(score), product)
        if previous is not None and key < previous:
            raise BridgeError("ranking_violation")
        previous = key
        products.add(product)
        images.add(image)
        matches.append(RankedVisualMatch(rank, product, image, float(score)))
    return VisualSearch(source_system, "openclip", embedding_version, tuple(matches))
