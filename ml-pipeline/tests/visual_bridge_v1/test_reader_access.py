import asyncio
import base64
import io
import json
import os
import secrets
import subprocess
import uuid
from dataclasses import replace

import httpx
import numpy as np
import pytest
from PIL import Image

from integration.visual_bridge_v1.bridge import VisualIntegrationBridge
from integration.visual_bridge_v1.catalogue import ReadOnlyCatalogue
from integration.visual_bridge_v1.reader_access import (
    ACCESS_ID,
    ACCESS_SQL,
    VIEW,
    ReaderAccessError,
    apply_access,
    business_fingerprint,
    main,
    protect_private_config,
    scram_verifier,
    verify_access,
    write_private_config,
)
from sahulat_api.app import create_app
from sahulat_api.settings import HttpSettings
from sahulat_database.migrations import query_json, run_psql
from sahulat_visual.domain import ImageRecord
from sahulat_visual.index import InMemoryVectorIndex
from sahulat_visual.retrieval import VisualRetrievalService
from tests.database.test_catalog_core_schema import seeded_database
from tests.visual_bridge_v1.test_catalogue import reader_config, search
from tests.visual_bridge_v1.test_client import client


@pytest.fixture(scope="module")
def scoped_reader(seeded_database):
    # Only a generated test database/role, never the live fixture or runtime password.
    admin = seeded_database
    assert admin.database.startswith("sahulat_ai_m001_test_")
    name = "sahulat_visual_test_" + uuid.uuid4().hex[:12]
    password = secrets.token_urlsafe(32)
    before = business_fingerprint(admin)
    apply_access(admin, reader_role=name, password=password)
    assert before == business_fingerprint(admin)
    reader = replace(admin, user=name, password=password)
    try:
        run_psql(
            admin,
            sql="""
            INSERT INTO catalog.product_external_refs(
                product_id, source_system, external_product_id)
            VALUES ('00000000-0000-7000-8000-000000000003','synthetic-v1','A'),
                   ('00000000-0000-7000-8000-000000000004','synthetic-v1','B');
            INSERT INTO catalog.product_images(id,product_id,storage_key,mime_type)
            VALUES ('00000000-0000-7000-8000-000000000061',
                    '00000000-0000-7000-8000-000000000003','synthetic/a.png','image/png'),
                   ('00000000-0000-7000-8000-000000000062',
                    '00000000-0000-7000-8000-000000000004','synthetic/b.png','image/png');
            INSERT INTO catalog.image_external_refs(image_id,source_system,external_image_id)
            VALUES ('00000000-0000-7000-8000-000000000061','synthetic-v1','A/image_1.png'),
                   ('00000000-0000-7000-8000-000000000062','synthetic-v1','B/image_1.png');
        """,
        )
        yield admin, reader
    finally:
        # This role owns no objects. Revoke only its test grants before dropping the test role.
        run_psql(admin, sql=f'DROP OWNED BY "{name}"; DROP ROLE "{name}";')


@pytest.mark.unit
def test_scram_stored_secret_encoding_is_deterministic_and_salted():
    encoded = scram_verifier("synthetic-ASCII-password", salt=b"a" * 16)
    assert encoded == scram_verifier("synthetic-ASCII-password", salt=b"a" * 16)
    assert encoded != scram_verifier("synthetic-ASCII-password", salt=b"b" * 16)
    mechanism, settings, keys = encoded.split("$")
    assert mechanism == "SCRAM-SHA-256" and settings.startswith("4096:")
    assert all(len(base64.b64decode(key)) == 32 for key in keys.split(":"))
    assert "synthetic-ASCII-password" not in encoded


@pytest.mark.unit
@pytest.mark.parametrize(
    "password,salt,iterations",
    [
        ("non-ASCII-\u2603", b"a" * 16, 4096),
        ("control\ncharacter", b"a" * 16, 4096),
        ("ASCII", b"short", 4096),
        ("ASCII", b"a" * 16, 1),
    ],
)
def test_invalid_scram_inputs_fail_closed(password, salt, iterations):
    with pytest.raises(ReaderAccessError, match="invalid_scram_input"):
        scram_verifier(password, salt=salt, iterations=iterations)


@pytest.mark.unit
def test_credential_file_is_private_exclusive_and_consistent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / ".env.visual-reader"
    config = reader_config()
    write_private_config(path, config)
    content = path.read_text(encoding="utf-8")
    assert "DATABASE_USER=synthetic_reader\n" in content
    assert "DATABASE_PASSWORD=synthetic-only\n" in content
    assert ":synthetic-only@localhost:5432/" in content
    with pytest.raises(ReaderAccessError, match="credential_creation_failed"):
        write_private_config(path, replace(config, password="should-not-overwrite"))
    assert path.read_text(encoding="utf-8") == content


@pytest.mark.unit
def test_secrets_cannot_be_generated_into_a_trackable_filename(tmp_path):
    with pytest.raises(ReaderAccessError, match="unsafe_credential_filename"):
        write_private_config(tmp_path / "tracked.env", reader_config())


@pytest.mark.unit
@pytest.mark.skipif(os.name != "nt", reason="Windows ACL integrity")
def test_existing_untrusted_explicit_credential_acl_fails_closed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / ".env.visual-reader"
    write_private_config(path, reader_config())
    subprocess.run(["icacls", str(path), "/grant", "*S-1-1-0:R"], capture_output=True, check=True)
    try:
        with pytest.raises(ReaderAccessError, match="credential_acl_untrusted"):
            protect_private_config(path)
    finally:
        subprocess.run(
            ["icacls", str(path), "/remove:g", "*S-1-1-0"], capture_output=True, check=True
        )
    protect_private_config(path)


@pytest.mark.unit
def test_admin_verification_is_rejected_before_connecting(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Administrative credentials must be rejected early")

    monkeypatch.setattr("integration.visual_bridge_v1.reader_access.run_psql", forbidden)
    with pytest.raises(ReaderAccessError, match="reader_verification_failed"):
        verify_access(replace(reader_config(), user="postgres"))


@pytest.mark.unit
def test_secret_verifier_is_private_stdin_and_errors_are_sanitized(monkeypatch):
    calls = []

    def fail(*args, **kwargs):
        calls.append(kwargs)
        raise subprocess.CalledProcessError(1, ["psql"], stderr="SECRET verifier internal")

    monkeypatch.setattr(
        "integration.visual_bridge_v1.reader_access.query_json", lambda *args: "4096"
    )
    monkeypatch.setattr("integration.visual_bridge_v1.reader_access.run_psql", fail)
    with pytest.raises(ReaderAccessError, match="reader_provisioning_failed") as error:
        apply_access(
            reader_config(), reader_role="sahulat_visual_reader", password="synthetic-only"
        )
    assert "SCRAM-SHA-256$" in calls[0]["stdin_sql"]
    assert "synthetic-only" not in calls[0]["stdin_sql"]
    assert "reader_password_verifier" not in calls[0]["variables"]
    assert "SECRET" not in str(error.value)


@pytest.mark.unit
def test_missing_reader_credential_reference_is_safe(tmp_path, capsys):
    assert main(["verify", "--reader-env", str(tmp_path / "missing")]) == 2
    assert json.loads(capsys.readouterr().out) == {
        "status": "RED",
        "error": "reader_credential_reference_required",
    }


@pytest.mark.database
def test_role_connects_with_scram_and_has_only_the_resolution_view(scoped_reader):
    admin, reader = scoped_reader
    result = verify_access(reader)
    assert result["least_privilege"] and result["reader_role"] == reader.user
    assert result["projection_rows"] == 2
    surface = query_json(
        reader,
        """
        SELECT jsonb_agg(n.nspname || '.' || c.relname ORDER BY n.nspname,c.relname)
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname IN ('iam','catalog','inventory','integration','audit')
          AND c.relkind IN ('r','p','v','m','f')
          AND has_any_column_privilege(current_user,c.oid,'SELECT');
    """,
    )
    assert surface == [VIEW]
    flags = query_json(
        admin,
        f"""
        SELECT to_jsonb(r) - 'rolpassword' FROM pg_roles r WHERE rolname='{reader.user}';
    """,
    )
    assert flags["rolcanlogin"] and not flags["rolinherit"]
    assert not any(
        flags[key]
        for key in ["rolsuper", "rolcreatedb", "rolcreaterole", "rolreplication", "rolbypassrls"]
    )


@pytest.mark.database
def test_projection_has_only_approved_fields_and_owner_rights(scoped_reader):
    admin, reader = scoped_reader
    fields = query_json(
        admin,
        """
        SELECT jsonb_agg(column_name ORDER BY ordinal_position) FROM information_schema.columns
        WHERE table_schema='catalog' AND table_name='visual_product_resolution_v1';
    """,
    )
    assert fields == [
        "source_system",
        "external_product_id",
        "external_image_id",
        "product_id",
        "image_id",
        "name",
        "description",
        "blocked",
    ]
    definition = query_json(admin, f"SELECT to_jsonb(pg_get_viewdef('{VIEW}'::regclass, true));")
    assert "image.product_id = product.id" in definition
    assert "image_ref.source_system = product_ref.source_system" in definition
    options = query_json(
        admin, f"SELECT to_jsonb(reloptions) FROM pg_class WHERE oid='{VIEW}'::regclass"
    )
    assert set(options) == {"security_barrier=true", "security_invoker=false"}
    assert query_json(reader, f"SELECT to_jsonb(count(*)) FROM {VIEW}") == 2


@pytest.mark.database
@pytest.mark.parametrize(
    "operation",
    [
        "INSERT INTO catalog.products(vendor_id,name,description) SELECT "
        "'00000000-0000-7000-8000-000000000002'::uuid,'Forbidden','Forbidden' WHERE false",
        "UPDATE catalog.products SET name=name WHERE false",
        "DELETE FROM catalog.products WHERE false",
        "TRUNCATE catalog.image_external_refs",
        "CREATE TABLE catalog.forbidden_reader_table(id integer)",
        "CREATE TABLE public.forbidden_reader_table(id integer)",
        "CREATE TEMP TABLE forbidden_reader_table(id integer)",
        "ALTER TABLE catalog.products ADD COLUMN forbidden_reader_column integer",
        "DROP VIEW catalog.visual_product_resolution_v1",
        "SELECT name FROM catalog.products",
        "SELECT email FROM iam.users",
        "SELECT before_data FROM audit.audit_log",
        "SELECT on_hand_quantity FROM inventory.inventory_balances",
        "SELECT payload FROM integration.outbox_events",
        "SELECT rolpassword FROM pg_authid",
        "SET ROLE postgres",
        "SET ROLE pg_read_all_data",
    ],
    ids=[
        "insert",
        "update",
        "delete",
        "truncate",
        "create-catalog",
        "create-public",
        "create-temp",
        "alter",
        "drop",
        "base-table-read",
        "iam-read",
        "audit-read",
        "inventory-read",
        "outbox-read",
        "credential-read",
        "admin-role",
        "broad-reader-role",
    ],
)
def test_prohibited_operations_fail_even_with_read_only_default_disabled(scoped_reader, operation):
    admin, reader = scoped_reader
    before = business_fingerprint(admin)
    # Tests never touch canonical fixtures: this is a generated DB and rollback is unconditional.
    output = run_psql(
        reader,
        stdin_sql="\\set VERBOSITY sqlstate\nBEGIN;\n"
        "SET TRANSACTION READ WRITE;\n" + operation + ";\nROLLBACK;\n",
        check=False,
    )
    assert output.returncode != 0 and "42501" in output.stderr
    assert business_fingerprint(admin) == before


@pytest.mark.database
@pytest.mark.parametrize(
    "unsafe,restore",
    [
        ("ALTER ROLE {role} SUPERUSER", "ALTER ROLE {role} NOSUPERUSER"),
        ("ALTER ROLE {role} CREATEDB", "ALTER ROLE {role} NOCREATEDB"),
        ("ALTER ROLE {role} CREATEROLE", "ALTER ROLE {role} NOCREATEROLE"),
        ("ALTER ROLE {role} REPLICATION", "ALTER ROLE {role} NOREPLICATION"),
        ("ALTER ROLE {role} BYPASSRLS", "ALTER ROLE {role} NOBYPASSRLS"),
        ("GRANT pg_read_all_data TO {role}", "REVOKE pg_read_all_data FROM {role}"),
        (
            "GRANT SELECT(name) ON catalog.products TO {role}",
            "REVOKE SELECT(name) ON catalog.products FROM {role}",
        ),
        (
            "GRANT UPDATE(name) ON catalog.products TO {role}",
            "REVOKE UPDATE(name) ON catalog.products FROM {role}",
        ),
        (
            "GRANT SELECT ON catalog.visual_product_resolution_v1 TO {role} WITH GRANT OPTION",
            "REVOKE GRANT OPTION FOR SELECT ON catalog.visual_product_resolution_v1 FROM {role}",
        ),
    ],
    ids=[
        "superuser",
        "createdb",
        "createrole",
        "replication",
        "bypassrls",
        "membership",
        "column-read",
        "column-write",
        "grant-option",
    ],
)
def test_privilege_drift_is_rejected_without_weakening_guards(scoped_reader, unsafe, restore):
    admin, reader = scoped_reader
    run_psql(admin, sql=unsafe.format(role=reader.user))
    try:
        with pytest.raises(ReaderAccessError):
            verify_access(reader)
    finally:
        run_psql(admin, sql=restore.format(role=reader.user))
    assert verify_access(reader)["least_privilege"]


@pytest.mark.database
def test_provisioning_is_checksum_idempotent_and_password_not_rotated(scoped_reader):
    admin, reader = scoped_reader
    before = business_fingerprint(admin)
    apply_access(admin, reader_role=reader.user, password="different-password-must-not-rotate")
    assert verify_access(reader)["least_privilege"]
    assert business_fingerprint(admin) == before
    assert (
        query_json(
            admin,
            f"SELECT to_jsonb(count(*)) FROM integration.schema_migrations "
            f"WHERE migration_id='{ACCESS_ID}'",
        )
        == 1
    )


@pytest.mark.database
def test_checksum_drift_fails_closed(scoped_reader, tmp_path):
    admin, reader = scoped_reader
    changed = tmp_path / "changed.sql"
    changed.write_text(
        ACCESS_SQL.read_text(encoding="utf-8") + "\n-- unapproved drift\n", encoding="utf-8"
    )
    with pytest.raises(ReaderAccessError, match="reader_provisioning_failed"):
        apply_access(admin, reader_role=reader.user, password="synthetic-only", artifact=changed)
    assert verify_access(reader)["least_privilege"]


@pytest.mark.database
def test_live_test_db_identity_resolution_preserves_rank_and_scores(scoped_reader):
    admin, reader = scoped_reader
    before = business_fingerprint(admin)
    resolved = asyncio.run(ReadOnlyCatalogue(reader).resolve(search()))
    assert [match.rank for match in resolved] == [1, 2]
    assert [match.score for match in resolved] == [0.9, 0.6]
    assert [match.product.name for match in resolved] == ["Product One", "Product Two"]
    assert business_fingerprint(admin) == before


@pytest.mark.database
def test_existing_fastapi_bridge_to_real_test_db_preserves_ranking(scoped_reader, encoder):
    admin, reader = scoped_reader
    encoder.identity = replace(
        encoder.identity, model_name="openclip", embedding_version="synthetic-openclip-v1"
    )
    index = InMemoryVectorIndex(
        encoder.identity,
        np.array([[1, 0, 0], [0.8, 0.6, 0]]),
        [
            ImageRecord("A/image_1.png", "A", "synthetic/a.png"),
            ImageRecord("B/image_1.png", "B", "synthetic/b.png"),
        ],
        {"dataset_version": "synthetic-v1"},
    )
    app = create_app(
        HttpSettings("synthetic-v1"), service_factory=lambda: VisualRetrievalService(encoder, index)
    )
    image = io.BytesIO()
    Image.new("RGB", (32, 32), (255, 0, 0)).save(image, format="PNG")
    before = business_fingerprint(admin)

    async def scenario():
        async with app.router.lifespan_context(app):
            async with client(httpx.ASGITransport(app)) as api:
                resolved = await VisualIntegrationBridge(api, ReadOnlyCatalogue(reader)).search(
                    image.getvalue(), mime_type="image/png"
                )
                assert [match.product.name for match in resolved] == ["Product One", "Product Two"]
                assert [match.rank for match in resolved] == [1, 2]
                assert resolved[0].score == 1

    asyncio.run(scenario())
    assert before == business_fingerprint(admin)
