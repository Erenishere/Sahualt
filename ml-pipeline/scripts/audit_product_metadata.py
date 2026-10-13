import argparse
from pathlib import Path

from sahulat_text.metadata_audit import audit_product_metadata, write_audit_artifacts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit Khaadi metadata against ADR-DATA-001")
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("data/raw/khaadi/Khaadi_Data/khaadi_data.csv"),
    )
    parser.add_argument("--manifest", type=Path, default=Path("data/khaadi/manifest.json"))
    parser.add_argument("--source-metadata", type=Path, default=Path("data/khaadi/source.json"))
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path("artifacts/product_metadata_audit/product_metadata_audit.json"),
    )
    parser.add_argument(
        "--report-output", type=Path, default=Path("reports/product_metadata_audit.md")
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    audit = audit_product_metadata(
        args.csv,
        source_path=args.csv.as_posix(),
        manifest_path=args.manifest,
        manifest_source_path=args.manifest.as_posix(),
        source_metadata_path=args.source_metadata,
        source_metadata_source_path=args.source_metadata.as_posix(),
    )
    write_audit_artifacts(audit, args.json_output, args.report_output)
    print(
        "product_metadata_audit_completed",
        f"status={audit['contract_fitness']['overall_readiness_verdict']}",
        f"parsed_rows={audit['source']['parsed_rows']}",
        "json=" + args.json_output.as_posix(),
        "report=" + args.report_output.as_posix(),
    )


if __name__ == "__main__":
    main()
