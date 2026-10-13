"""Shared, semantics-preserving ADR-DATA-001 normalization."""

from __future__ import annotations

import re
import unicodedata

NORMALIZATION_VERSION = "product-normalization-v1"
UNICODE_VERSION = "15.0.0"


def normalization_steps(value: str) -> tuple[str, dict[str, bool]]:
    unicode_value = unicodedata.normalize("NFKC", value)
    # Replace controls with separators, matching Gate 1; never join adjacent words.
    without_controls = "".join(
        " " if unicodedata.category(character) == "Cc" else character for character in unicode_value
    )
    trimmed = without_controls.strip()
    collapsed = re.sub(r"\s+", " ", trimmed)
    return collapsed, {
        "unicode_normalization": unicode_value != value,
        "control_character_removal": without_controls != unicode_value,
        "outer_whitespace_trimming": trimmed != without_controls,
        "repeated_whitespace_collapse": collapsed != trimmed,
    }


def normalize_text(value: str) -> str:
    return normalization_steps(value)[0]


def require_document_unicode_version() -> None:
    """Fail rather than silently build v1 with different Unicode normalization tables."""
    if unicodedata.unidata_version != UNICODE_VERSION:
        raise ValueError(f"product-text-v1 requires Unicode {UNICODE_VERSION} (Python 3.12)")
