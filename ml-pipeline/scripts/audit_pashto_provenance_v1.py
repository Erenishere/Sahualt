"""Audit the evidence required before promoting Pashto Ghag."""

import json
from pathlib import Path

from sahulat_voice.alternatives.metadata import (
    ASSET_OUTPUT,
    CONFIG,
    candidates,
    validate_official,
    verified_assets,
)
from sahulat_voice.benchmark.io import file_sha256, put_json, read_canonical_json

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/pashto_provenance_v1/audit.json"
KEY = "pashto-ghag"


def main() -> int:
    record = candidates(ROOT)[KEY]
    official = read_canonical_json(ROOT / ASSET_OUTPUT / f"{KEY}-official-metadata.json")
    readme = (ROOT / ASSET_OUTPUT / f"{KEY}-README.md").read_bytes()
    acquisition = verified_assets(ROOT, KEY)
    validate_official(record, official, readme)
    text = readme.decode("utf-8").casefold()
    manifest = ROOT / "artifacts/pashto_provenance_v1/training_manifest.json"
    overlap = ROOT / "artifacts/pashto_provenance_v1/fleurs_overlap_audit.json"
    attestation = ROOT / "artifacts/pashto_provenance_v1/provenance_attestation.json"
    checks = {
        "exact_revision": official.get("sha") == record["revision"],
        "apache_2_license": record["license"] == "apache-2.0"
        and official.get("cardData", {}).get("license") == "apache-2.0",
        "declared_training_dataset_is_common_voice": record["declared_datasets"]
        == ["mozilla-foundation/common_voice_17_0"],
        "fleurs_not_declared": "fleurs" not in text,
        "weights_hash_verified": bool(acquisition["files"]),
        "complete_training_manifest_supplied": manifest.exists(),
        "fleurs_overlap_audit_supplied": overlap.exists(),
        "publisher_provenance_attestation_supplied": attestation.exists(),
    }
    report = {
        "gate": "PASHTO-PROVENANCE-V1",
        "status": "GREEN" if all(checks.values()) else "NOT_GREEN",
        "candidate": record,
        "checks": checks,
        "missing_evidence": [
            name
            for name, passed in checks.items()
            if not passed
        ],
        "frozen_assets": {
            "revision": record["revision"],
            "license": record["license"],
            "weights_sha256": record["weights_sha256"],
            "weights_bytes": record["weights_bytes"],
            "config_sha256": file_sha256(ROOT / CONFIG),
        },
        "decision": (
            "Pashto Ghag may proceed to production-candidate review."
            if all(checks.values())
            else "Do not promote; obtain the missing provenance and overlap evidence."
        ),
    }
    put_json(OUTPUT, report)
    print(json.dumps(report))
    return 0 if report["status"] == "GREEN" else 2


if __name__ == "__main__":
    raise SystemExit(main())
