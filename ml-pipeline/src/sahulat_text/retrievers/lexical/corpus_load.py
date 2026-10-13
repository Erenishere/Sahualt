from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from sahulat_text.documents.builder import build_product_document
from sahulat_text.documents.corpus import DEFAULT_REGISTRY, verify_registered_corpus
from sahulat_text.documents.projection import CanonicalProductProjection

from .index import LexicalIndexDocument


def toy_lexical_documents(*, corpus_sha256: str = "b" * 64) -> tuple[LexicalIndexDocument, ...]:
    projections = (
        CanonicalProductProjection(
            UUID("00000000-0000-7000-8000-000000000101"),
            "Red cotton shirt",
            "Lightweight red cotton shirt for casual wear.",
            ("Red",),
        ),
        CanonicalProductProjection(
            UUID("00000000-0000-7000-8000-000000000102"),
            "Blue running shoes",
            "Comfortable blue shoes for daily running.",
            ("Blue",),
        ),
        CanonicalProductProjection(
            UUID("00000000-0000-7000-8000-000000000103"),
            "Black leather bag",
            "Compact black leather bag.",
            tuple(),
        ),
    )
    return tuple(
        LexicalIndexDocument(
            document.product_id,
            document.text,
            corpus_sha256.removeprefix("sha256:"),
        )
        for document in (build_product_document(projection) for projection in projections)
    )


def load_lexical_documents_from_registry(
    registry_path: Path = DEFAULT_REGISTRY,
    *,
    repository_root: Path = Path("."),
) -> tuple[LexicalIndexDocument, ...]:
    registry = verify_registered_corpus(registry_path, repository_root=repository_root)
    artifact_path = repository_root / registry["artifact_path"]
    payload = artifact_path.read_bytes()
    corpus_sha256 = registry["artifact_sha256"]
    expected_count = registry["record_count"]
    rows: list[LexicalIndexDocument] = []
    for position, line in enumerate(payload.splitlines(), start=1):
        if not line.strip():
            raise ValueError(f"corpus row {position}: empty line")
        record = json.loads(line)
        text = record.get("text")
        product_id = record.get("product_id")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"corpus row {position}: missing text")
        if not isinstance(product_id, str):
            raise ValueError(f"corpus row {position}: missing product_id")
        rows.append(
            LexicalIndexDocument(
                UUID(product_id),
                text,
                corpus_sha256,
            )
        )
    if len(rows) != expected_count:
        raise ValueError(
            f"corpus record count mismatch: expected {expected_count}, found {len(rows)}"
        )
    identities = [row.product_id for row in rows]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate product_id in frozen corpus artifact")
    return tuple(sorted(rows, key=lambda row: str(row.product_id)))
