import ast
import hashlib
import json
from pathlib import Path

import pytest

from sahulat_api.app import create_app

pytestmark = pytest.mark.unit


def test_versioned_openapi_snapshot_matches_exact_runtime_contract():
    expected = Path("configs/api/visual-http-v1.openapi.json").read_bytes()
    manifest = json.loads(Path("configs/api/visual-http-v1.manifest.json").read_text())
    current = (
        json.dumps(create_app().openapi(), ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    assert current == expected
    assert hashlib.sha256(expected).hexdigest() == manifest["openapi_sha256"]
    assert manifest["contract_version"] == "visual-http-v1"
    assert manifest["identity_scope"] == "external"
    assert manifest["status"] == "FROZEN"


def test_runtime_is_independent_of_text_and_annotation_packages():
    for path in Path("src/sahulat_api").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                modules.append(node.module or "")
            elif isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
        assert not any(m.startswith("sahulat_text") for m in modules)
        assert not any("evaluation" in m or "ingestion" in m for m in modules)
        if path.name != "catalogue.py":
            assert not any(m.startswith("sahulat_database") for m in modules)
