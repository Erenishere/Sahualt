"""Download/import public Khaadi v1 and map image folders to actual CSV product IDs."""

import argparse
import csv
import hashlib
import json
import shutil
import urllib.request
import zipfile
from pathlib import Path

SOURCE = "usman8/khaadis-clothes-data-with-images"
URL = f"https://www.kaggle.com/api/v1/datasets/download/{SOURCE}?datasetVersionNumber=1"
SHA256 = "f268adbd70a165d1c1ed820ce68968aa6e4954581eb44496c9b508b813c3064e"


def prepare(archive: Path, output: Path, manifest: Path) -> None:
    if not archive.exists():
        archive.parent.mkdir(parents=True, exist_ok=True)
        partial = archive.with_suffix(".partial")
        with urllib.request.urlopen(URL, timeout=120) as response, partial.open("wb") as stream:
            shutil.copyfileobj(response, stream)
        partial.replace(archive)
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != SHA256:
        raise ValueError(
            "Archive differs from frozen public v1 checksum; do not reuse this protocol"
        )
    root = output.resolve()
    with zipfile.ZipFile(archive) as package:
        if sum(info.file_size for info in package.infolist()) > 1_000_000_000:
            raise ValueError("Unexpected archive expansion size")
        for info in package.infolist():
            target = (root / info.filename).resolve()
            if not target.is_relative_to(root) or info.filename.startswith(("/", "\\")):
                raise ValueError("Unsafe archive path")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with package.open(info) as source, target.open("wb") as dest:
                shutil.copyfileobj(source, dest)
    csv_path = root / "Khaadi_Data/khaadi_data.csv"
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        products = list(csv.DictReader(stream))
    known_ids: set[str] = set()
    rows = []
    missing = []
    for product in products:
        product_id = product["ID"].strip()
        if not product_id or product_id in known_ids:
            raise ValueError("Missing or duplicate CSV product ID")
        known_ids.add(product_id)
        folder = (csv_path.parent / product["Img Path"].replace("\\", "/")).resolve()
        if not folder.is_relative_to(root) or folder.name != product_id:
            raise ValueError("CSV image folder does not agree with product ID")
        files = sorted(p for p in folder.iterdir() if p.is_file()) if folder.is_dir() else []
        if not files:
            missing.append(product_id)
        for path in files:
            relative = path.relative_to(root).as_posix()
            rows.append(
                {
                    "image_id": f"{product_id}/{path.name}",
                    "product_id": product_id,
                    "image_path": relative,
                }
            )
    mapped = {r["image_path"] for r in rows}
    orphaned = [
        p.relative_to(root).as_posix()
        for p in (root / "Khaadi_Data/images").rglob("*")
        if p.is_file() and p.relative_to(root).as_posix() not in mapped
    ]
    # Include orphans as invalid metadata so the audit accounts for every image file.
    rows += [{"image_id": p, "product_id": "", "image_path": p} for p in orphaned]
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    provenance = {
        "source": SOURCE,
        "dataset_version": "1",
        "source_url": URL,
        "archive_sha256": digest,
        "archive_bytes": archive.stat().st_size,
        "product_records": len(products),
        "image_records": len(rows),
        "products_without_images": missing,
        "orphaned_images": orphaned,
    }
    manifest.with_name("source.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(provenance, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=Path("data/raw/khaadi-v1.zip"))
    parser.add_argument("--output", type=Path, default=Path("data/raw/khaadi"))
    parser.add_argument("--manifest", type=Path, default=Path("data/khaadi/manifest.json"))
    args = parser.parse_args()
    prepare(args.archive, args.output, args.manifest)
