from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from sahulat_visual.errors import ConfigurationError, DatasetError
from sahulat_visual.evaluation.comparison import compare, paired_intervals
from sahulat_visual.evaluation.protocol import load_protocol
from sahulat_visual.io import write_json

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "section,key,value",
    [
        ("metrics", "ap_denominator", "total-relevant"),
        ("ranking", "ties", "random"),
        ("audit", "cross_product_duplicates", "keep"),
        ("runtime", "precision", "fp16"),
        ("split", "query_fraction", 1.0),
        ("runtime", "batch_size", 1.5),
        ("split", "seed", True),
    ],
)
def test_unsupported_protocol_semantics_fail(tmp_path, section, key, value):
    config = load_protocol(Path("configs/eval_visual_v1.yaml"))
    config[section][key] = value
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    with pytest.raises(ConfigurationError):
        load_protocol(path)


def test_comparison_refuses_different_split(tmp_path):
    result = {
        "model": "openclip",
        "evaluation_version": "EVAL-VISUAL-V1",
        "dataset_fingerprint": "same",
        "audit_sha256": "same",
        "split_sha256": "first",
    }
    other = deepcopy(result)
    other.update(model="fashionclip", split_sha256="second")
    write_json(tmp_path / "a.json", result)
    write_json(tmp_path / "b.json", other)
    with pytest.raises(DatasetError, match="split_sha256"):
        compare(tmp_path / "a.json", tmp_path / "b.json", tmp_path / "comparison.md")


def test_paired_uncertainty_known_constant_difference():
    a = [
        {
            "query": {"image_id": str(i), "product_id": str(i // 2)},
            "metrics": {"precision_at_1": 0.0, "map_at_5": 0.25},
        }
        for i in range(6)
    ]
    b = deepcopy(a)
    for row in b:
        row["metrics"].update(precision_at_1=1.0, map_at_5=0.75)
    result = paired_intervals(a, b, replicates=100)
    assert result["metrics"]["precision_at_1"] == {"delta": 1.0, "ci95_low": 1.0, "ci95_high": 1.0}
    assert result["metrics"]["map_at_5"]["delta"] == 0.5


def test_paired_uncertainty_rejects_different_queries():
    with pytest.raises(DatasetError):
        paired_intervals([{"query": {"image_id": "a"}}], [{"query": {"image_id": "b"}}])
