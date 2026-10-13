import shutil
from pathlib import Path

import pytest
from PIL import Image

from sahulat_visual.dataset import audit_dataset, freeze_split, make_split, verify_split
from sahulat_visual.errors import DatasetError, InvalidImageError
from sahulat_visual.evaluation.protocol import load_protocol
from sahulat_visual.images import ImagePolicy, load_image

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("content", [b"", b"not an image", b"GIF89a"])
def test_invalid_image(content):
    with pytest.raises(InvalidImageError):
        load_image(content)


def test_actual_format_over_extension(image_file):
    path = image_file("not-a-jpeg.jpg", format="PNG")
    assert load_image(path).mode == "RGB"
    with pytest.raises(InvalidImageError):
        load_image(path, ImagePolicy(allowed_formats=("JPEG",)))


def test_size_and_dimensions(image_file):
    path = image_file("a.png")
    for policy in (ImagePolicy(max_bytes=2), ImagePolicy(max_pixels=100), ImagePolicy(min_side=64)):
        with pytest.raises(InvalidImageError):
            load_image(path, policy)


def test_missing_image(tmp_path):
    with pytest.raises(InvalidImageError):
        load_image(tmp_path / "missing.png")


def test_audit_duplicates_conflicts_and_missing(image_file, tmp_path):
    a = image_file("a.png")
    shutil.copyfile(a, tmp_path / "b.png")
    image_file("c.png", (10, 200, 30))
    shutil.copyfile(tmp_path / "c.png", tmp_path / "d.png")
    rows = [
        {"image_id": n, "product_id": p, "image_path": f"{n}.png"}
        for n, p in [("a", "A"), ("b", "A"), ("c", "B"), ("d", "C"), ("e", "D")]
    ]
    rows.append({"image_id": "f", "product_id": "", "image_path": "f.png"})
    result = audit_dataset(rows, tmp_path)
    assert result["retained_images"] == 1
    reasons = [r["reason"] for r in result["excluded"]]
    assert reasons.count("within-product-exact-duplicate") == 1
    assert reasons.count("conflicting-product-label") == 2
    assert "missing-file" in reasons
    assert "missing-or-invalid-metadata" in reasons


def test_pixel_duplicate_different_encoding(image_file, tmp_path):
    path = image_file("a.png")
    with Image.open(path) as im:
        im.save(tmp_path / "b.png", compress_level=0)
    rows = [{"image_id": n, "product_id": "A", "image_path": f"{n}.png"} for n in ["a", "b"]]
    result = audit_dataset(rows, tmp_path)
    assert not result["binary_duplicate_groups"]
    assert len(result["pixel_duplicate_groups"]) == 1
    assert result["retained_images"] == 1


def test_unsafe_path_is_reported(tmp_path):
    result = audit_dataset(
        [{"image_id": "a", "product_id": "A", "image_path": "../a.png"}], tmp_path
    )
    assert result["excluded"][0]["reason"] == "unsafe-path"


def test_repeated_image_ids_fail(tmp_path):
    row = {"image_id": "a", "product_id": "A", "image_path": "a.png"}
    with pytest.raises(DatasetError):
        audit_dataset([row, row], tmp_path)


def test_split_deterministic_and_content_bound(image_file, tmp_path):
    config = load_protocol(Path("configs/eval_visual_v1.yaml"))
    rows = []
    for i in range(5):
        path = image_file(f"{i}.png", (i * 30, 20, 50))
        rows.append(
            {"image_id": str(i), "product_id": "A" if i < 4 else "B", "image_path": path.name}
        )
    audit = audit_dataset(rows, tmp_path)
    split = freeze_split(tmp_path / "split.json", audit, config)
    assert make_split(audit, config) == split
    assert not set(split["query_ids"]) & set(split["gallery_ids"])
    assert split["statistics"]["singleton_gallery_only_products"] == ["B"]
    assert freeze_split(tmp_path / "split.json", audit, config) == split
    image_file("0.png", (255, 255, 255))
    with pytest.raises(DatasetError):
        verify_split(split, audit_dataset(rows, tmp_path), config)
