import os
import re
from dataclasses import dataclass
from pathlib import Path

from sahulat_visual.images import DEFAULT_POLICY


@dataclass(frozen=True)
class HttpSettings:
    source_system: str
    index_path: Path | None = None
    index_sha256: str = ""
    max_concurrent_requests: int = 1
    body_timeout_seconds: float = 15.0
    max_request_bytes: int = DEFAULT_POLICY.max_bytes + 64 * 1024

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_-]{1,63}", self.source_system):
            raise ValueError("AI_VISUAL_SOURCE_SYSTEM must be an explicit source namespace")
        if type(self.max_concurrent_requests) is not int or self.max_concurrent_requests < 1:
            raise ValueError("AI_MAX_CONCURRENT_REQUESTS must be positive")
        if not 0 < self.body_timeout_seconds <= 300:
            raise ValueError("AI_BODY_TIMEOUT_SECONDS must be in (0, 300]")
        if type(self.max_request_bytes) is not int or self.max_request_bytes < 1:
            raise ValueError("max_request_bytes must be positive")
        if self.index_path is not None and not re.fullmatch(r"[0-9a-f]{64}", self.index_sha256):
            raise ValueError("AI_VISUAL_INDEX_SHA256 must pin the supplied index bytes")

    @classmethod
    def from_env(cls) -> "HttpSettings":
        return cls(
            source_system=os.getenv("AI_VISUAL_SOURCE_SYSTEM", ""),
            index_path=Path(os.environ["AI_VISUAL_INDEX_PATH"])
            if os.getenv("AI_VISUAL_INDEX_PATH")
            else None,
            index_sha256=os.getenv("AI_VISUAL_INDEX_SHA256", ""),
            max_concurrent_requests=int(os.getenv("AI_MAX_CONCURRENT_REQUESTS", "1")),
            body_timeout_seconds=float(os.getenv("AI_BODY_TIMEOUT_SECONDS", "15")),
        )
