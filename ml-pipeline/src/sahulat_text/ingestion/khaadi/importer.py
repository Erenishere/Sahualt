from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sahulat_database.migrations import DatabaseConfig

from ..canonical import content_checksum, semantic_checksum, vendor_uuid
from ..postgres import ImportExecution, import_canonical_batch, verify_batch_parity
from .mapper import IMPORTER_VERSION, KhaadiMappingResult, map_khaadi_fixture
from .reader import KhaadiAuthority, load_khaadi_authority

DB_CONTRACT_VERSION = "DB-CONTRACT-V1"
MIGRATION_VERSION = "20260910_001_catalog_core_v1"
IMPORT_MANIFEST_VERSION = "fixture-ingestion-v1-evidence"


class KhaadiIngestionError(RuntimeError):
    """Raised when Fixture Ingestion V1 cannot complete or prove parity."""


def _execution_dict(execution: ImportExecution) -> dict[str, Any]:
    return {
        "start_state": dict(sorted(execution.start_state.items())),
        "created": dict(sorted(execution.created.items())),
        "end_state": dict(sorted(execution.end_state.items())),
        "no_op": execution.is_no_op,
    }


def build_import_manifest(
    authority: KhaadiAuthority,
    mapping: KhaadiMappingResult,
    first_run: ImportExecution,
    second_run: ImportExecution,
    parity: dict[str, Any],
) -> dict[str, Any]:
    batch = mapping.batch
    idempotency_checks = {
        "second_run_created_nothing": second_run.is_no_op,
        "second_run_state_unchanged": second_run.start_state == second_run.end_state,
        "first_and_second_end_state_equal": first_run.end_state == second_run.end_state,
        "outbox_unchanged": (
            first_run.start_state["outbox_events"]
            == first_run.end_state["outbox_events"]
            == second_run.end_state["outbox_events"]
        ),
    }
    image_exclusions = [
        {
            "image_id": item.get("image_id"),
            "product_id": item.get("product_id"),
            "reason": item.get("reason"),
        }
        for item in sorted(
            mapping.excluded_images,
            key=lambda item: (str(item.get("image_id")), str(item.get("reason"))),
        )
    ]
    payload: dict[str, Any] = {
        "manifest_version": IMPORT_MANIFEST_VERSION,
        "importer_version": IMPORTER_VERSION,
        "status": (
            "GREEN" if parity["status"] == "GREEN" and all(idempotency_checks.values()) else "RED"
        ),
        "source": {
            "source_system": batch.external_source,
            "dataset_version": authority.dataset_version,
            "csv_path": authority.source_path_record,
            "csv_sha256": authority.source_sha256,
            "manifest_path": authority.manifest_path_record,
            "manifest_sha256": authority.manifest_sha256,
            "visual_audit_sha256": authority.visual_audit_sha256,
        },
        "contracts": {
            "gate_1_audit_version": authority.audit["audit_version"],
            "gate_1_evidence_sha256": authority.audit["evidence_sha256"],
            "db_contract_version": DB_CONTRACT_VERSION,
            "migration_version": MIGRATION_VERSION,
        },
        "fixture_vendor": {
            "id": str(vendor_uuid(batch.external_source)),
            "display_name": batch.vendor_display_name,
            "slug": batch.vendor_slug,
            "synthetic_fixture_infrastructure": True,
            "source_derived_vendor_metadata": False,
        },
        "mapping": [
            {
                "source": "ID",
                "destination": "catalog.product_external_refs.external_product_id",
            },
            {"source": "Product Name", "destination": "catalog.products.name"},
            {
                "source": "Product Description",
                "destination": "catalog.products.description",
            },
            {"source": "Color", "destination": "catalog.product_variants.color"},
            {"source": "Price", "destination": "catalog.listings.price"},
            {
                "source": "Availability",
                "destination": "catalog.listings.availability",
                "explicit_alias": {"In Stock": "in_stock"},
            },
            {
                "source": "EVAL-VISUAL-V1 retained image",
                "destination": "catalog.product_images + catalog.image_external_refs",
            },
        ],
        "policies": {
            "uuid_strategy": (
                "UUIDv5 from a fixed Fixture Ingestion V1 namespace, source system, entity type, "
                "and external identity"
            ),
            "transaction": "one PostgreSQL transaction for the complete fixture",
            "reconciliation": (
                "unchanged records no-op; source checksum drift or conflicting canonical "
                "state fails"
            ),
            "inventory": "no inventory row; absence means stock was not supplied",
            "listing_status": "draft because authoritative currency is absent",
            "image_scope": "product-level; the source does not assert variant-specific images",
            "outbox": "suppressed for evaluation/bootstrap import",
        },
        "classifications": {
            "source_products": mapping.source_products,
            "attempted_products": len(mapping.importable_product_ids),
            "importable_products": len(mapping.importable_product_ids),
            "importable_product_ids": list(mapping.importable_product_ids),
            "quarantined_products": len(mapping.quarantined_products),
            "quarantined": list(mapping.quarantined_products),
            "rejected_products": len(mapping.rejected_products),
            "rejected": list(mapping.rejected_products),
        },
        "image_mapping": {
            "raw_manifest_images": mapping.raw_images,
            "retained_and_imported_images": mapping.retained_images,
            "visual_v1_excluded_images": len(mapping.excluded_images),
            "exclusions": image_exclusions,
        },
        "first_run": _execution_dict(first_run),
        "second_run": _execution_dict(second_run),
        "idempotency": {
            "status": "GREEN" if all(idempotency_checks.values()) else "RED",
            "checks": idempotency_checks,
        },
        "parity": parity,
        "counts": {
            **parity["counts"],
            "draft_listings": parity["counts"]["listings"],
            "default_variants": parity["counts"]["variants"],
        },
        "semantic_checksum": semantic_checksum(batch),
        "import_result_checksum": parity["import_result_checksum"],
        "limitations": [
            "The fixture vendor is synthetic structural infrastructure, not dataset metadata.",
            "Currency, Size, Brand, Category, and numeric Stock are not supplied or inferred.",
            "Only the 2,093 images retained by locked Visual V1 are imported; 16 "
            "duplicate/conflicting images remain excluded.",
            "The current local database login is administrative; runtime least-privilege "
            "roles remain a later platform task.",
        ],
        "forbidden_work": {
            "search_created": False,
            "fts_created": False,
            "vector_created": False,
            "commerce_created": False,
            "outbox_events_emitted": False,
            "product_text_v1_created": False,
        },
    }
    return {**payload, "manifest_checksum": f"sha256:{content_checksum(payload)}"}


def render_import_report(manifest: dict[str, Any]) -> str:
    counts = manifest["counts"]
    source = manifest["source"]
    classifications = manifest["classifications"]
    parity = manifest["parity"]
    lines = [
        "# Fixture Ingestion V1",
        "",
        f"Status: **{manifest['status']}**  ",
        f"Importer: `{manifest['importer_version']}`  ",
        f"Source: `{source['csv_path']}`  ",
        f"Source SHA-256: `{source['csv_sha256']}`  ",
        f"Semantic checksum: `{manifest['semantic_checksum']}`  ",
        f"Import result checksum: `{manifest['import_result_checksum']}`",
        "",
        "## Authority and disposition",
        "",
        f"- Dataset version: `{source['dataset_version']}`",
        f"- Gate 1: `{manifest['contracts']['gate_1_audit_version']}`",
        f"- DB contract: `{manifest['contracts']['db_contract_version']}`",
        f"- Source products: {classifications['source_products']}",
        f"- Importable: {classifications['importable_products']}",
        f"- Quarantined: {classifications['quarantined_products']}",
        f"- Rejected: {classifications['rejected_products']}",
        "",
        "## Canonical mapping",
        "",
        "| Source | Destination |",
        "| --- | --- |",
    ]
    lines.extend(f"| {item['source']} | `{item['destination']}` |" for item in manifest["mapping"])
    lines.extend(
        [
            "",
            "Availability uses the explicitly frozen fixture alias `In Stock -> in_stock`.",
            "This is protocol normalization, not inferred stock quantity.",
            "",
            "## Imported state",
            "",
            f"- Products: {counts['products']}",
            f"- Default variants: {counts['default_variants']}",
            f"- Draft listings: {counts['draft_listings']}",
            f"- Inventory rows: {counts['inventory']}",
            f"- Product images: {counts['images']}",
            f"- Product external refs: {counts['product_external_refs']}",
            f"- Image external refs: {counts['image_external_refs']}",
            "",
            "Images follow locked Visual V1: 2,109 manifest records, 2,093 retained/imported,",
            "and 16 duplicate/conflicting records excluded. Images are product-level because the",
            "source does not assert variant-specific ownership.",
            "",
            "## Parity and idempotency",
            "",
            f"- Field parity: **{parity['status']}**",
            f"- Idempotency: **{manifest['idempotency']['status']}**",
            "- Second-run inserts: 0 across Vendor, Product, Variant, Listing, Image, "
            "and external refs",
            "- Outbox events emitted: 0",
            "",
            "All required semantic fields equal the normalized audited source. `brand_name`,",
            "`category_id`, Size, Currency, and Inventory remain NULL/absent. Generated UUIDs and",
            "timestamps are excluded from the semantic checksum.",
            "",
            "## Limitations",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in manifest["limitations"])
    lines.extend(
        [
            "",
            f"Evidence checksum: `{manifest['manifest_checksum']}`.",
            "",
        ]
    )
    return "\n".join(lines)


def _stable_evidence(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": manifest["status"],
        "source": manifest["source"],
        "contracts": manifest["contracts"],
        "fixture_vendor": manifest["fixture_vendor"],
        "classifications": manifest["classifications"],
        "image_mapping": manifest["image_mapping"],
        "counts": manifest["counts"],
        "semantic_checksum": manifest["semantic_checksum"],
        "import_result_checksum": manifest["import_result_checksum"],
    }


def write_import_evidence(
    manifest: dict[str, Any], *, json_path: Path, markdown_path: Path
) -> bool:
    if json_path.exists():
        existing = json.loads(json_path.read_text(encoding="utf-8"))
        existing_payload = {
            key: value for key, value in existing.items() if key != "manifest_checksum"
        }
        if existing.get("manifest_checksum") != f"sha256:{content_checksum(existing_payload)}":
            raise KhaadiIngestionError("Existing Fixture Ingestion V1 evidence checksum is invalid")
        if _stable_evidence(existing) != _stable_evidence(manifest):
            raise KhaadiIngestionError(
                "Existing Fixture Ingestion V1 evidence conflicts with DB state"
            )
        if not markdown_path.exists():
            markdown_path.parent.mkdir(parents=True, exist_ok=True)
            markdown_path.write_text(render_import_report(existing), encoding="utf-8")
        return False
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_import_report(manifest), encoding="utf-8")
    return True


def execute_khaadi_ingestion(
    config: DatabaseConfig,
    *,
    repository_root: Path = Path("."),
    verify_image_binaries: bool = True,
) -> dict[str, Any]:
    authority = load_khaadi_authority(repository_root, verify_image_binaries=verify_image_binaries)
    mapping = map_khaadi_fixture(authority)
    first_run = import_canonical_batch(config, mapping.batch)
    first_parity = verify_batch_parity(config, mapping.batch)
    if first_parity["status"] != "GREEN":
        raise KhaadiIngestionError("Gate 1 to PostgreSQL parity failed after import")
    second_run = import_canonical_batch(config, mapping.batch)
    parity = verify_batch_parity(config, mapping.batch)
    manifest = build_import_manifest(authority, mapping, first_run, second_run, parity)
    if manifest["status"] != "GREEN":
        raise KhaadiIngestionError("Fixture Ingestion V1 evidence did not reach GREEN")
    return manifest
