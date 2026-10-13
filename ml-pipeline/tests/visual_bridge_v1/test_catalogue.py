import asyncio
import json
import re
from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pytest

from integration.visual_bridge_v1.catalogue import ReadOnlyCatalogue, resolve_snapshot, snapshot_sql
from integration.visual_bridge_v1.errors import BridgeError
from integration.visual_bridge_v1.models import parse_search
from sahulat_database.migrations import DatabaseConfig
from tests.visual_bridge_v1.test_client import search_payload

pytestmark = pytest.mark.unit


def search():
    return parse_search(
        search_payload(),
        source_system="synthetic-v1",
        embedding_version="synthetic-openclip-v1",
        top_k=5,
    )


def snapshot():
    return {
        "permission_ok": True,
        "rows": [
            {
                "source_system": "synthetic-v1",
                "external_product_id": "B",
                "external_image_id": "B/image_1.png",
                "product_id": str(UUID(int=100)),
                "image_id": str(UUID(int=2)),
                "name": "Synthetic B",
                "description": "Original B description",
                "blocked": False,
            },
            {
                "source_system": "synthetic-v1",
                "external_product_id": "A",
                "external_image_id": "A/image_1.png",
                "product_id": str(UUID(int=200)),
                "image_id": str(UUID(int=1)),
                "name": "Synthetic A",
                "description": "Original A description",
                "blocked": False,
            },
        ],
    }


def reader_config():
    # Synthetic only; this is not a supplied live credential or an actual database role.
    return DatabaseConfig(
        "localhost", 5432, "synthetic_test", "synthetic_reader", "synthetic-only", Path("psql")
    )


def test_canonical_resolution_preserves_scores_order_and_minimal_projection():
    result = resolve_snapshot(search(), snapshot())
    assert [r.rank for r in result] == [1, 2]
    assert [r.score for r in result] == [0.9, 0.6]
    assert [r.product.product_id for r in result] == [UUID(int=200), UUID(int=100)]
    assert result[0].canonical_image_id == UUID(int=1)
    assert result[0].product.name == "Synthetic A"
    assert result[0].product.description == "Original A description"
    assert set(result[0].product.__dataclass_fields__) == {"product_id", "name", "description"}


@pytest.mark.parametrize(
    "fault,expected",
    [
        ("missing", "canonical_resolution_failure"),
        ("unknown_uuid", "catalog_state_invalid"),
        ("bad_uuid", "canonical_resolution_failure"),
        ("cross_product", "canonical_resolution_failure"),
        ("wrong_namespace", "canonical_resolution_failure"),
        ("duplicate_image", "canonical_resolution_failure"),
        ("extra_rows", "ambiguous_identity"),
        ("duplicate_canonical", "canonical_resolution_failure"),
        ("archived", "catalog_state_invalid"),
        ("name_missing", "catalog_state_invalid"),
        ("description_missing", "catalog_state_invalid"),
        ("leaked_fields", "catalog_state_invalid"),
        ("permission", "database_permission_rejected"),
    ],
)
def test_catalogue_integrity_fails_closed(fault, expected):
    data = snapshot()
    rows = data["rows"]
    if fault == "missing":
        rows.pop()
    elif fault == "unknown_uuid":
        del rows[0]["product_id"]
    elif fault == "bad_uuid":
        rows[0]["product_id"] = "not-a-uuid"
    elif fault == "cross_product":
        rows[0]["external_product_id"] = "C"
    elif fault == "wrong_namespace":
        rows[0]["source_system"] = "wrong-v1"
    elif fault == "duplicate_image":
        rows[0] = dict(rows[1])
    elif fault == "extra_rows":
        rows.append(dict(rows[0]))
    elif fault == "duplicate_canonical":
        rows[0]["product_id"] = rows[1]["product_id"]
        rows[0]["name"] = rows[1]["name"]
        rows[0]["description"] = rows[1]["description"]
    elif fault == "archived":
        rows[0]["blocked"] = True
    elif fault == "name_missing":
        rows[0]["name"] = " "
    elif fault == "description_missing":
        rows[0]["description"] = None
    elif fault == "leaked_fields":
        rows[0]["price"] = 12
    else:
        data["permission_ok"] = False
    with pytest.raises(BridgeError, match=expected):
        resolve_snapshot(search(), data)


def test_postgres_application_config_is_rejected_without_connecting():
    with pytest.raises(BridgeError, match="database_permission_rejected"):
        ReadOnlyCatalogue(replace(reader_config(), user="postgres"))


def test_uuid_shaped_unknown_external_product_is_never_guessed_to_be_canonical():
    payload = search_payload()
    payload["results"] = [
        {"product_id": str(UUID(int=999)), "matched_image_id": "unknown/image.png", "score": 0.9}
    ]
    ranked = parse_search(
        payload, source_system="synthetic-v1", embedding_version="synthetic-openclip-v1", top_k=5
    )
    with pytest.raises(BridgeError, match="canonical_resolution_failure"):
        resolve_snapshot(ranked, {"permission_ok": True, "rows": []})


def test_sql_is_read_only_scoped_and_guarded_before_business_read():
    script = snapshot_sql(reader_config(), search())
    assert script.startswith("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;")
    assert script.index("\\if :bridge_permissions_allowed") < script.index(
        "JOIN catalog.visual_product_resolution_v1"
    )
    assert "rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls" in script
    assert "has_any_column_privilege" in script
    assert "resolution.external_product_id = wanted.external_product_id" in script
    assert "resolution.external_image_id = wanted.external_image_id" in script
    projection = Path("database/provisioning/20260912_001_catalog_reader_access_v1.sql").read_text(
        encoding="utf-8"
    )
    assert "image.product_id = product.id" in projection
    assert "image_ref.source_system = product_ref.source_system" in projection
    assert "CREATE,TEMPORARY" in script and "pg_auth_members" in script
    assert not re.search(
        r"^\s*(INSERT|UPDATE|DELETE|TRUNCATE|ALTER|CREATE|DROP|GRANT)\b", script, re.M
    )
    assert not any(
        name in script
        for name in ["catalog.listings", "inventory.inventory_balances", "price", "currency"]
    )


class ProcessDouble:
    def __init__(self, *, data=None, returncode=0, delay=0):
        self.returncode = None
        self.final_returncode = returncode
        self.data = snapshot() if data is None else data
        self.delay = delay
        self.inputs = []
        self.killed = False

    async def communicate(self, content=None):
        self.inputs.append(content)
        if not self.killed:
            await asyncio.sleep(self.delay)
        self.returncode = -9 if self.killed else self.final_returncode
        return json.dumps(self.data).encode(), b"SECRET internal-db-error"

    def kill(self):
        self.killed = True


def test_executor_read_only_permissions_transport_and_no_secret_output(monkeypatch):
    process = ProcessDouble()
    calls = []

    async def create(*args, **kwargs):
        calls.append((args, kwargs))
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create)
    result = asyncio.run(ReadOnlyCatalogue(reader_config()).resolve(search()))
    assert len(result) == 2
    command, options = calls[0]
    assert "-X" in command and "-qAt" in command and "ON_ERROR_STOP=1" in command
    assert "synthetic-only" not in command
    assert "default_transaction_read_only=on" in options["env"]["PGOPTIONS"]
    assert "statement_timeout=10000" in options["env"]["PGOPTIONS"]
    assert process.inputs[0].startswith(b"BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;")


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("auth_failed", "database_unavailable"),
        ("bad_permission", "database_permission_rejected"),
        ("timeout", "database_timeout"),
        ("missing_client", "database_unavailable"),
    ],
)
def test_database_failures_are_safe(mode, expected, monkeypatch):
    process = ProcessDouble(
        returncode=1 if mode == "auth_failed" else 0,
        data={"permission_ok": False, "rows": []} if mode == "bad_permission" else None,
        delay=0.05 if mode == "timeout" else 0,
    )

    async def create(*args, **kwargs):
        if mode == "missing_client":
            raise FileNotFoundError("SECRET C:/private")
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create)

    async def scenario():
        with pytest.raises(BridgeError, match=expected):
            await ReadOnlyCatalogue(reader_config(), timeout_seconds=0.01).resolve(search())

    asyncio.run(scenario())
    if mode == "timeout":
        assert process.killed


def test_database_cancellation_kills_inflight_process(monkeypatch):
    process = ProcessDouble(delay=10)
    started = asyncio.Event()

    async def create(*args, **kwargs):
        started.set()
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create)

    async def scenario():
        task = asyncio.create_task(ReadOnlyCatalogue(reader_config()).resolve(search()))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert process.killed

    asyncio.run(scenario())
