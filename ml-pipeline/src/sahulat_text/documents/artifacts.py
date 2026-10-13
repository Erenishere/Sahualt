from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterable
from pathlib import Path
from time import perf_counter
from typing import Any

from sahulat_database.migrations import (
    MIGRATION_ID,
    MIGRATION_PATH,
    DatabaseConfig,
    migration_checksum,
    query_json,
)
from sahulat_text.normalization import NORMALIZATION_VERSION, UNICODE_VERSION, normalize_text

from .builder import (
    BUILDER_VERSION,
    SCHEMA_VERSION,
    SORT_POLICY,
    ProductTextDocument,
    build_product_documents,
    serialize_documents,
)
from .projection import CanonicalProductProjection, DocumentContractError
from .repository import load_product_projection_snapshot
from .serialization import canonical_json_bytes, sha256

ADR_VERSION = "ADR-ML-004-v1"
ADR_STATUS = "ACCEPTED"


def verify_document_parity(
    projections: Iterable[CanonicalProductProjection], documents: Iterable[ProductTextDocument]
) -> dict[str, Any]:
    source = list(projections)
    built = list(documents)
    by_id = {projection.product_id: projection for projection in source}
    checks = {
        "one_document_per_eligible_product": (
            len(source) == len(built) == len(by_id)
            and len({document.product_id for document in built}) == len(built)
            and set(by_id) == {document.product_id for document in built}
        ),
        "name_parity": True,
        "description_parity": True,
        "color_parity": True,
        "text_rendering_parity": True,
        "semantic_fields_only": True,
        "document_checksums_valid": True,
    }
    for document in built:
        projection = by_id.get(document.product_id)
        if projection is None:
            continue
        name = normalize_text(projection.name)
        description = normalize_text(projection.description)
        colors = sorted(set(filter(None, map(normalize_text, projection.colors))))
        expected_text = f"Product Name: {name}\nDescription: {description}"
        if colors:
            expected_text += "\nColor: " + ", ".join(colors)
        checks["name_parity"] &= document.name == name
        checks["description_parity"] &= document.description == description
        checks["color_parity"] &= list(document.colors) == colors
        checks["text_rendering_parity"] &= document.text == expected_text
        checks["semantic_fields_only"] &= set(document.payload()["fields"]) == {
            "name",
            "description",
            "colors",
        }
        checks["document_checksums_valid"] &= (
            sha256(canonical_json_bytes(document.payload())) == document.document_checksum
        )
    return {"status": "GREEN" if all(checks.values()) else "RED", "checks": checks}


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def verify_jsonl_artifact(path: Path, documents: Iterable[ProductTextDocument]) -> str:
    expected = serialize_documents(documents)
    actual = path.read_bytes()
    if actual != expected:
        raise DocumentContractError("JSONL artifact bytes differ from canonical document batch")
    # Validate persisted records and checksums independently of file-writing mechanics.
    for line in actual.splitlines():
        record = json.loads(line)
        checksum = record.pop("document_checksum")
        if checksum != sha256(canonical_json_bytes(record)):
            raise DocumentContractError("persisted document checksum mismatch")
    return sha256(actual)


def render_build_report(evidence: dict[str, Any]) -> str:
    manifest = evidence["manifest"]
    counts = manifest["counts"]
    observations = evidence["observations"]
    lineage = manifest["fixture_lineage"]
    provenance_lines = ["## Fixture provenance", ""]
    if lineage is None:
        provenance_lines += ["No fixture lineage requested; the canonical builder needs none.", ""]
    else:
        provenance_lines += [
            f"- Source namespace: `{lineage['source_system']}`",
            f"- Source SHA-256: `{lineage['source_sha256']}`",
            f"- Gate 1 version: `{lineage['gate_1_version']}`",
            f"- Verified fixture semantic checksum: `{lineage['fixture_semantic_checksum']}`",
            "",
        ]
    return "\n".join(
        [
            "# product-text-v1 canonical build",
            "",
            f"Gate status: **{evidence['status']}**  ",
            f"ADR: **{ADR_VERSION} / {ADR_STATUS}**  ",
            f"Source contract: `{manifest['db_contract_version']}`  ",
            f"Source migration: `{MIGRATION_ID}`  ",
            f"Artifact checksum: `{manifest['artifact_checksum']}`",
            "",
            "## Projection and normalization",
            "",
            "`CanonicalProductProjection(product_id: UUID, name: str, description: str, "
            "colors: tuple[str, ...])` is immutable and fixture-independent.",
            "",
            "One read-only PostgreSQL statement loads Product and applicable non-archived "
            "ProductVariant colors. Non-archived draft/published/paused Products are included; "
            "this is document eligibility, not commercial search eligibility. Archived Products "
            "are excluded; malformed required semantics abort the entire build.",
            "",
            f"Normalization: `{NORMALIZATION_VERSION}`, Unicode `{UNICODE_VERSION}`; NFKC, "
            "Cc controls replaced with spaces, outer trimming and whitespace collapse. Language, "
            "punctuation and case are preserved. Colors are normalized, deduplicated and "
            "Unicode code-point sorted, then joined with comma + space; "
            "free-text values are not split.",
            "",
            "Fields: Name -> Description -> optional Color. Missing Color has no text line; "
            "machine `colors` is an empty list. No placeholders or inferred metadata.",
            "",
            "Excluded: Price, Currency, Availability, Stock, Size, Brand, Category, Vendor, SKU, "
            "listing state, images, tags and external IDs. Product UUID is record identity only. "
            "Source prose is preserved, not redacted if it happens to mention these concepts.",
            "",
            *provenance_lines,
            "## Measured counts",
            "",
            "| Measure | Count |",
            "| --- | ---: |",
            *[f"| {key.replace('_', ' ')} | {value} |" for key, value in sorted(counts.items())],
            "",
            "## Verification",
            "",
            f"- DB/document field parity: **{evidence['parity']['status']}**",
            f"- Two independent DB loads/builds, JSONL bytes and artifact checksums: "
            f"**{'GREEN' if evidence['determinism'] else 'RED'}**",
            "- Per-document SHA-256 and persisted JSONL checksums: **GREEN**",
            "- Pure builder works without external refs, images, Listing or Inventory.",
            "- PostgreSQL remains business truth; JSONL is derived reproducibility evidence.",
            "",
            "## Observations (not performance gates)",
            "",
            f"- Products loaded: {counts['canonical_products_read']}",
            f"- Load duration: {observations['load_seconds']:.6f} s",
            f"- Document-build duration: {observations['build_seconds']:.6f} s",
            f"- Artifact-write duration: {observations['artifact_write_seconds']:.6f} s",
            f"- JSONL size: {manifest['output_bytes']} bytes",
            "",
            "## Limitations and next gates",
            "",
            "Unicode 15.0.0 tables (Python 3.12) are required for v1 builds; different tables "
            "fail explicitly rather than silently change normalization. Derived manifests contain "
            "no durations or timestamps; observational evidence is intentionally run-specific.",
            "",
            "Runtime least-privilege database roles remain a platform task. This gate reads but "
            "does not modify the database, fixture ingestion, or Visual V1. Retrieval was not "
            "implemented: no Search schema/tables, FTS, vectors, embeddings, RRF or Commerce.",
            "",
            "EVAL-TEXT-V1 still needs a frozen protocol/query set and human relevance judgments. "
            "ADR-ML-002 still needs an accepted PostgreSQL lexical configuration "
            "and implementation scope.",
            "",
        ]
    )


def build_database_artifacts(
    config: DatabaseConfig,
    *,
    output_directory: Path = Path("artifacts/product_documents"),
    report_path: Path = Path("reports/product_text_v1_build.md"),
    fixture_lineage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    started = perf_counter()
    snapshot = load_product_projection_snapshot(config)
    loaded = perf_counter()
    if snapshot.migrations != ((MIGRATION_ID, migration_checksum(MIGRATION_PATH)),):
        raise DocumentContractError("source migration history does not match DB-CONTRACT-V1")
    documents = build_product_documents(snapshot.projections)
    payload = serialize_documents(documents)
    built = perf_counter()
    parity = verify_document_parity(snapshot.projections, documents)
    repeated = load_product_projection_snapshot(config)
    repeated_payload = serialize_documents(build_product_documents(repeated.projections))
    deterministic = (
        snapshot.products_read == repeated.products_read
        and snapshot.excluded_product_ids == repeated.excluded_product_ids
        and snapshot.migrations == repeated.migrations
        and payload == repeated_payload
        and sha256(payload) == sha256(repeated_payload)
    )
    forbidden = query_json(
        config,
        """
        SELECT jsonb_build_object(
            'search_schema', to_regnamespace('search') IS NOT NULL,
            'commerce_schema', to_regnamespace('commerce') IS NOT NULL,
            'analytics_schema', to_regnamespace('analytics') IS NOT NULL,
            'vector_extension', EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector'),
            'fts_or_vector_columns', EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_schema IN ('catalog', 'inventory', 'integration', 'iam', 'audit')
                  AND udt_name IN ('tsvector', 'tsquery', 'vector')),
            'search_indexes', EXISTS (SELECT 1 FROM pg_class AS c
                JOIN pg_am AS am ON am.oid = c.relam
                JOIN pg_namespace AS n ON n.oid = c.relnamespace
                WHERE n.nspname IN ('catalog', 'inventory', 'integration', 'iam', 'audit')
                  AND am.amname IN ('gin', 'hnsw', 'ivfflat'))
        );
    """,
    )
    if parity["status"] != "GREEN" or not deterministic or any(forbidden.values()):
        raise DocumentContractError("document parity/determinism/infrastructure gate failed")
    manifest = {
        "manifest_version": "product-text-v1-manifest-v1",
        "document_schema_version": SCHEMA_VERSION,
        "normalization_version": NORMALIZATION_VERSION,
        "unicode_version": UNICODE_VERSION,
        "builder_version": BUILDER_VERSION,
        "db_contract_version": "DB-CONTRACT-V1",
        "adr_version": ADR_VERSION,
        "adr_status": ADR_STATUS,
        "source_migrations": [
            {"migration_id": migration_id, "checksum": checksum}
            for migration_id, checksum in snapshot.migrations
        ],
        "fixture_lineage": fixture_lineage,
        "sort_policy": SORT_POLICY,
        "serialization": "sorted keys; compact JSON; UTF-8 without BOM; LF after every record",
        "artifact_checksum": sha256(payload),
        "output_bytes": len(payload),
        "counts": {
            "canonical_products_read": snapshot.products_read,
            "eligible_products": len(snapshot.projections),
            "documents_generated": len(documents),
            "excluded_products": len(snapshot.excluded_product_ids),
            "products_with_color": sum(bool(document.colors) for document in documents),
            "products_without_color": sum(not document.colors for document in documents),
            "multi_color_products": sum(len(document.colors) > 1 for document in documents),
        },
        "excluded_product_ids": [str(value) for value in snapshot.excluded_product_ids],
        "document_checksums": {
            str(document.product_id): document.document_checksum for document in documents
        },
    }
    manifest["manifest_checksum"] = sha256(canonical_json_bytes(manifest))
    write_started = perf_counter()
    jsonl_path = output_directory / f"{SCHEMA_VERSION}.jsonl"
    atomic_write(jsonl_path, payload)
    atomic_write(
        output_directory / f"{SCHEMA_VERSION}.manifest.json", canonical_json_bytes(manifest) + b"\n"
    )
    artifact_write_seconds = perf_counter() - write_started
    verify_jsonl_artifact(jsonl_path, documents)
    evidence = {
        "evidence_version": "product-text-v1-build-v1",
        "status": "GREEN",
        "manifest": manifest,
        "parity": parity,
        "determinism": deterministic,
        "forbidden_infrastructure": forbidden,
        "observations": {
            "load_seconds": loaded - started,
            "build_seconds": built - loaded,
            "artifact_write_seconds": artifact_write_seconds,
        },
    }
    atomic_write(
        output_directory / f"{SCHEMA_VERSION}-build.json", canonical_json_bytes(evidence) + b"\n"
    )
    atomic_write(report_path, render_build_report(evidence).encode("utf-8"))
    return evidence
