from pathlib import Path
from typing import Any

import yaml

from ..dataset import audit_dataset, read_manifest
from ..encoders.factory import MODEL_SPECS
from ..errors import ConfigurationError
from ..images import ImagePolicy


def load_protocol(path: Path) -> dict[str, Any]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ConfigurationError("Evaluation config must be a mapping")
    try:
        integer_settings = [
            config["split"]["seed"],
            config["runtime"]["seed"],
            config["runtime"]["batch_size"],
            config["runtime"]["num_workers"],
            config["runtime"]["warmup_images"],
        ]
        supported = (
            config["evaluation_version"] == "EVAL-VISUAL-V1"
            and all(type(value) is int for value in integer_settings)
            and config["relevance"] == "exact-product-id-equality"
            and config["metrics"]
            == {
                "k": 5,
                "precision_denominator": "k",
                "ap_denominator": "min-k-total-relevant",
                "ndcg": "binary-log2-rank-plus-one",
                "mrr": "full-gallery",
            }
            and config["ranking"]
            == {
                "similarity": "normalized-float32-inner-product",
                "ties": "image-id-ascending",
                "evaluation_unit": "image",
            }
            and config["split"]["method"] == "per-product-sha256-floor-v1"
            and config["split"]["singleton_policy"] == "gallery-only"
            and config["split"]["provenance"] == "new-split-not-historical"
            and config["audit"]["policy"] == "binary-and-exif-rgb-sha256-v1"
            and config["audit"]["within_product_duplicates"]
            == "retain-lexicographically-first-image-id"
            and config["audit"]["cross_product_duplicates"] == "exclude-all-members"
            and 0 < config["split"]["query_fraction"] < 1
            and config["runtime"]["precision"] == "fp32"
            and config["runtime"]["query_timing"]
            == "serial-single-image-includes-validation-preprocessing-transfer"
            and config["runtime"]["batch_size"] > 0
            and config["runtime"]["num_workers"] >= 0
            and config["runtime"]["warmup_images"] >= 0
            and config["models"] == MODEL_SPECS
        )
    except (KeyError, TypeError) as exc:
        raise ConfigurationError("Incomplete evaluation protocol") from exc
    if not supported:
        raise ConfigurationError("Unsupported or inconsistent EVAL-VISUAL-V1 semantics")
    return config


def config_path(config_file: Path, relative: str) -> Path:
    return (config_file.resolve().parent / relative).resolve()


def image_policy(config: dict[str, Any]) -> ImagePolicy:
    fields = ImagePolicy.__dataclass_fields__
    values = {key: value for key, value in config["audit"].items() if key in fields}
    values["allowed_formats"] = tuple(values["allowed_formats"])
    return ImagePolicy(**values)


def audit_protocol(config: dict[str, Any], config_file: Path) -> dict[str, Any]:
    return audit_dataset(
        read_manifest(config_path(config_file, config["dataset"]["manifest"])),
        config_path(config_file, config["dataset"]["root"]),
        image_policy(config),
    )
