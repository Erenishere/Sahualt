import argparse
import ast
import asyncio
import json
from pathlib import Path

import pytest

from integration.visual_bridge_v1 import cli, smoke
from integration.visual_bridge_v1.catalogue import resolve_snapshot
from integration.visual_bridge_v1.errors import BridgeError
from sahulat_visual.errors import IndexCompatibilityError
from tests.visual_bridge_v1.test_catalogue import search, snapshot

pytestmark = pytest.mark.unit


def test_cli_missing_credential_file_never_falls_back_to_shared_environment(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Missing explicit reader configuration must not fall back")

    monkeypatch.setattr(cli, "load_database_config", forbidden)
    with pytest.raises(BridgeError, match="invalid_configuration_or_image"):
        asyncio.run(cli.run(argparse.Namespace(database_env=tmp_path / "missing.env")))


def test_cli_success_exposes_only_ranked_canonical_identity_metadata(tmp_path, monkeypatch):
    credential_path = tmp_path / "synthetic.env"
    credential_path.write_text("# No live credentials\n", encoding="utf-8")
    calls = []

    class SyntheticAPI:
        def __init__(self, *args, **kwargs):
            calls.append("client")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            calls.append("close")

        async def health(self):
            calls.append("health")

        async def readiness(self):
            calls.append("readiness")

        async def search(self, content, **kwargs):
            assert content == b"unchanged-input"
            return search()

    class SyntheticReader:
        def __init__(self, config):
            pass

        async def resolve(self, ranked):
            return resolve_snapshot(ranked, snapshot())

    monkeypatch.setattr(cli, "VisualAIClient", SyntheticAPI)
    monkeypatch.setattr(cli, "ReadOnlyCatalogue", SyntheticReader)
    monkeypatch.setattr(cli, "load_database_config", lambda **kwargs: None)
    monkeypatch.setattr(cli, "read_bytes", lambda *args: b"unchanged-input")
    args = argparse.Namespace(
        database_env=credential_path,
        image=Path("synthetic.png"),
        mime_type="image/png",
        top_k=5,
        api_url="http://127.0.0.1:8000",
        source_system="synthetic-v1",
        embedding_version="synthetic-openclip-v1",
        timeout=30,
    )
    output = asyncio.run(cli.run(args))
    assert output["status"] == "VERIFIED" and output["catalog_writes"] == 0
    assert [row["rank"] for row in output["results"]] == [1, 2]
    assert all(
        set(row) == {"rank", "product_id", "matched_image_id", "score"} for row in output["results"]
    )
    assert calls == ["client", "health", "readiness", "close"]


@pytest.mark.parametrize("mode", ["failure", "cancellation"])
def test_cli_failure_and_cancellation_are_safe(mode, monkeypatch, capsys):
    async def fail(args):
        if mode == "cancellation":
            raise asyncio.CancelledError
        raise BridgeError("database_unavailable")

    monkeypatch.setattr(cli, "run", fail)
    code = cli.main(
        [
            "--source-system",
            "synthetic-v1",
            "--embedding-version",
            "synthetic-openclip-v1",
            "--database-env",
            "synthetic.env",
            "--image",
            "synthetic.png",
            "--mime-type",
            "image/png",
        ]
    )
    assert code == (130 if mode == "cancellation" else 2)
    result = json.loads(capsys.readouterr().out)
    assert set(result) == {"status", "error"}
    assert result["error"] == ("cancelled" if mode == "cancellation" else "database_unavailable")


@pytest.mark.parametrize(
    "failure",
    [OSError("SECRET path"), IndexCompatibilityError("SECRET model path"), RuntimeError("SECRET")],
)
def test_smoke_configuration_failures_do_not_leak_internals(failure, monkeypatch, capsys):
    async def fail(*args):
        raise failure

    monkeypatch.setattr(smoke, "cached_smoke", fail)
    assert (
        smoke.main(
            [
                "--index",
                "synthetic.npz",
                "--index-sha256",
                "0" * 64,
                "--source-system",
                "synthetic-v1",
            ]
        )
        == 2
    )
    result = json.loads(capsys.readouterr().out)
    assert result == {"gate": "RED", "blocker": "smoke_configuration_or_service_failure"}


def test_bridge_import_boundary_does_not_take_ownership_of_other_workstreams():
    for source in Path("integration/visual_bridge_v1").glob("*.py"):
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                imports = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imports = [node.module or ""]
            else:
                continue
            assert not any(module.startswith("sahulat_text") for module in imports)
