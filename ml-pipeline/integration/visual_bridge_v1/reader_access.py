"""Isolated catalog-reader provisioning/verification; never application authentication."""

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.parse import quote

from sahulat_database.migrations import (
    DatabaseConfig,
    load_database_config,
    migration_checksum,
    query_json,
    run_psql,
)
from sahulat_database.verification import BUSINESS_TABLES

from .catalogue import PERMISSIONS_SQL, ReadOnlyCatalogue, sql_literal
from .errors import BridgeError

ACCESS_ID = "20260912_001_catalog_reader_access_v1"
ACCESS_SQL = Path("database/provisioning") / f"{ACCESS_ID}.sql"
READER_ROLE = "sahulat_visual_reader"
VIEW = "catalog.visual_product_resolution_v1"


class ReaderAccessError(Exception):
    """Safe operational code, without psql error text or credentials."""


def scram_verifier(password: str, *, salt: bytes, iterations: int = 4096) -> str:
    # PostgreSQL's SCRAM-SHA-256 stored-secret format, using stdlib crypto primitives.
    # Generated passwords are printable ASCII, avoiding ambiguous SASLprep transformations.
    if not password.isascii() or not password.isprintable() or not 4096 <= iterations <= 1000000:
        raise ReaderAccessError("invalid_scram_input")
    if len(salt) < 16:
        raise ReaderAccessError("invalid_scram_input")
    salted = hashlib.pbkdf2_hmac("sha256", password.encode("ascii"), salt, iterations)
    client = hmac.digest(salted, b"Client Key", "sha256")
    stored = hashlib.sha256(client).digest()
    server = hmac.digest(salted, b"Server Key", "sha256")

    def encoded(value: bytes) -> str:
        return base64.b64encode(value).decode("ascii")

    return f"SCRAM-SHA-256${iterations}:{encoded(salt)}${encoded(stored)}:{encoded(server)}"


def apply_access(
    admin: DatabaseConfig,
    *,
    reader_role: str,
    password: str,
    artifact: Path = ACCESS_SQL,
) -> None:
    if not re.fullmatch(r"sahulat_visual_(?:reader|test_[a-f0-9]{12})", reader_role):
        raise ReaderAccessError("invalid_reader_role")
    try:
        iterations = int(query_json(admin, "SELECT to_jsonb(current_setting('scram_iterations'))"))
        verifier = scram_verifier(password, salt=secrets.token_bytes(16), iterations=iterations)
        script = "\\set reader_password_verifier " + sql_literal(verifier) + "\n"
        script += artifact.read_text(encoding="utf-8")
        run_psql(
            admin,
            stdin_sql=script,
            variables={
                "reader_role": reader_role,
                "migration_id": ACCESS_ID,
                "migration_checksum": migration_checksum(artifact),
            },
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        raise ReaderAccessError("reader_provisioning_failed") from None


def protect_private_config(path: Path) -> None:
    if not re.fullmatch(r"\.env\.visual-reader(?:\.[a-z0-9_-]+)?", path.name):
        raise ReaderAccessError("unsafe_credential_filename")
    if path.is_symlink():
        raise ReaderAccessError("unsafe_credential_path")
    if path.resolve().parent != Path.cwd().resolve():
        raise ReaderAccessError("unsafe_credential_path")
    if os.name != "nt":
        path.chmod(0o600)
        return
    identity = subprocess.run(
        ["whoami", "/user", "/fo", "csv", "/nh"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    sid = re.search(r"S-1-5-21-\d+-\d+-\d+-\d+", identity)
    if sid is None:
        raise ReaderAccessError("credential_acl_failed")
    owner = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "(Get-Acl -LiteralPath '.').GetOwner("
            "[System.Security.Principal.SecurityIdentifier]).Value",
        ],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if not re.fullmatch(r"S-1-(?:\d+-)+\d+", owner):
        raise ReaderAccessError("credential_acl_failed")
    grants = [f"*{sid.group()}:F", "*S-1-5-18:F", "*S-1-5-32-544:F"]
    # Provisioning can run as a sandbox account; the actual workspace owner must still read it.
    if owner not in {sid.group(), "S-1-5-18", "S-1-5-32-544"}:
        grants.append(f"*{owner}:R")
    subprocess.run(
        ["icacls", str(path), "/inheritance:r", "/grant:r", *grants],
        capture_output=True,
        check=True,
    )
    principals = json.loads(
        subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                f"(Get-Acl -LiteralPath '{path.name}').Access | ForEach-Object {{ "
                "$_.IdentityReference.Translate("
                "[System.Security.Principal.SecurityIdentifier]).Value "
                "} | ConvertTo-Json -Compress",
            ],
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    allowed = {sid.group(), owner, "S-1-5-18", "S-1-5-32-544"}
    if (
        not isinstance(principals, list)
        or not principals
        or any(p not in allowed for p in principals)
    ):
        raise ReaderAccessError("credential_acl_untrusted")


def write_private_config(path: Path, config: DatabaseConfig) -> None:
    # Only new, ignored local credentials are generated; existing files are never overwritten.
    if not re.fullmatch(r"\.env\.visual-reader(?:\.[a-z0-9_-]+)?", path.name):
        raise ReaderAccessError("unsafe_credential_filename")
    if path.is_symlink() or path.resolve().parent != Path.cwd().resolve():
        raise ReaderAccessError("unsafe_credential_path")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            protect_private_config(path)
            url = (
                f"postgresql://{quote(config.user, safe='')}:{quote(config.password, safe='')}"
                f"@{config.host}:{config.port}/{quote(config.database, safe='')}"
            )
            stream.write(
                "# Local generated reader credential: never commit or print.\n"
                f"DATABASE_HOST={config.host}\nDATABASE_PORT={config.port}\n"
                f"DATABASE_NAME={config.database}\nDATABASE_USER={config.user}\n"
                f"DATABASE_PASSWORD={config.password}\nDATABASE_URL={url}\n"
            )
    except (OSError, subprocess.SubprocessError):
        raise ReaderAccessError("credential_creation_failed") from None


def verify_access(reader: DatabaseConfig) -> dict[str, Any]:
    try:
        ReadOnlyCatalogue(reader)  # Reuse the existing early administrative-account rejection.
        script = (
            "BEGIN READ ONLY;\n"
            + PERMISSIONS_SQL.format(user=sql_literal(reader.user))
            + "\\if :bridge_permissions_allowed\n"
            + "SELECT jsonb_build_object('least_privilege', "
            + ":'bridge_permissions_allowed'::boolean, "
            + "'database', current_database(), 'reader_role', current_user, "
            + f"'projection_rows', (SELECT count(*) FROM {VIEW}));\n"
            + "\\else\nSELECT jsonb_build_object('least_privilege', false);\n\\endif\nCOMMIT;\n"
        )
        output = run_psql(reader, stdin_sql=script).stdout
        result = next(json.loads(line) for line in output.splitlines() if line.startswith("{"))
        if not isinstance(result, dict) or result.get("least_privilege") is not True:
            raise ReaderAccessError("reader_privileges_invalid")
        return result
    except (BridgeError, OSError, ValueError, StopIteration, subprocess.SubprocessError):
        raise ReaderAccessError("reader_verification_failed") from None


def business_fingerprint(admin: DatabaseConfig) -> dict[str, Any]:
    pairs = []
    for table in BUSINESS_TABLES:
        pairs.append(
            sql_literal(table)
            + ", (SELECT jsonb_build_object('rows', count(*), 'hash', "
            + "md5(COALESCE(jsonb_agg(to_jsonb(r) ORDER BY to_jsonb(r)::text)::text, '[]'))) "
            + f"FROM {table} r)"
        )
    state = query_json(admin, "SELECT jsonb_build_object(" + ",".join(pairs) + ")")
    checksum = hashlib.sha256(
        json.dumps(state, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "checksum": checksum,
        "row_counts": {key: value["rows"] for key, value in state.items()},
    }


def provision(admin: DatabaseConfig, credential_path: Path) -> dict[str, Any]:
    try:
        before = business_fingerprint(admin)
        role_exists = query_json(
            admin,
            "SELECT to_jsonb(EXISTS(SELECT 1 FROM pg_roles WHERE rolname="
            + sql_literal(READER_ROLE)
            + "))",
        )
        if credential_path.is_file():
            reader = load_database_config(credential_path)
            if reader.user != READER_ROLE or (reader.host, reader.port, reader.database) != (
                admin.host,
                admin.port,
                admin.database,
            ):
                raise ReaderAccessError("conflicting_reader_configuration")
            if role_exists:
                # Existing credentials must authenticate; never silently reset an existing password.
                verify_access(reader)
            protect_private_config(credential_path)
        elif role_exists:
            raise ReaderAccessError("existing_reader_credential_reference_required")
        else:
            reader = replace(admin, user=READER_ROLE, password=secrets.token_urlsafe(32))
            write_private_config(credential_path, reader)
        apply_access(admin, reader_role=READER_ROLE, password=reader.password)
        result = verify_access(reader)
        after = business_fingerprint(admin)
        if before != after:
            raise ReaderAccessError("business_state_changed_during_provisioning")
        return {
            "access_version": ACCESS_ID,
            "role_reused": bool(role_exists),
            "business_rows_unchanged": True,
            "business_checksum": after["checksum"],
            "catalog_writes": 0,
            **result,
        }
    except (OSError, ValueError, subprocess.SubprocessError):
        raise ReaderAccessError("reader_provisioning_failed") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Provision/verify isolated visual catalog access")
    parser.add_argument("operation", choices=["provision", "verify"])
    parser.add_argument("--admin-env", type=Path, default=Path(".env"))
    parser.add_argument("--reader-env", type=Path, default=Path(".env.visual-reader"))
    args = parser.parse_args(argv)
    try:
        if args.operation == "provision":
            if not args.admin_env.is_file():
                raise ReaderAccessError("admin_credential_reference_required")
            result = provision(load_database_config(args.admin_env), args.reader_env)
        else:
            if not args.reader_env.is_file():
                raise ReaderAccessError("reader_credential_reference_required")
            result = verify_access(load_database_config(args.reader_env))
        print(json.dumps({"status": "GREEN", **result}, sort_keys=True))
        return 0
    except (ReaderAccessError, OSError, ValueError, subprocess.SubprocessError) as exc:
        code = str(exc) if isinstance(exc, ReaderAccessError) else "reader_access_failed"
        print(json.dumps({"status": "RED", "error": code}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
