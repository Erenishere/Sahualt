# Catalog Reader Access V1

Owner: Adeel's isolated ML/integration workstream. Status: **GREEN**.
Target: PostgreSQL 18.6, `sahulat_ai_dev`.
Provisioning identity: `20260912_001_catalog_reader_access_v1`.

## Access model

The initial audit found only `postgres`, no scoped runtime reader and no catalog read view.
Therefore this gate adds one purpose-specific view and one direct-login role:

```text
Existing Visual API -> existing typed bridge -> sahulat_visual_reader
  -> catalog.visual_product_resolution_v1
  -> canonical Product/Image external references and Catalog truth
```

No backend, authentication flow, table, retriever or new PostgreSQL schema is introduced.
Migration 001, DB-CONTRACT-V1, catalog ownership and fixture semantics are unchanged.
The bridge's private SQL now reads the view instead of directly accessing four base tables;
its response types, canonical-resolution helper, ranking and API contract remain unchanged.

## Exact read surface

Only `catalog.visual_product_resolution_v1` is selectable by the runtime in application schemas.
It exposes exactly these columns:

| Column | Meaning |
| --- | --- |
| `source_system` | Explicit external identity namespace |
| `external_product_id` | External Product identity, never a canonical PK |
| `external_image_id` | External Image identity, opaque rather than a filesystem path |
| `product_id` | Canonical Product UUID |
| `image_id` | Canonical Image UUID |
| `name` | Authoritative Product Name |
| `description` | Authoritative Product Description |
| `blocked` | Product or Image is archived; no lifecycle timestamps are exposed |

The non-updatable join view is owned by the administrative schema owner, not the reader, with
`security_barrier=true` and `security_invoker=false`. PostgreSQL checks the underlying tables
against the view owner's rights, so the reader requires no base-table SELECT grants.
See [PostgreSQL CREATE VIEW](https://www.postgresql.org/docs/18/sql-createview.html).

Underlying relationships are only Product external refs -> Product -> ProductImage -> Image
external refs. The image must belong to the Product, and both references must share a namespace.
The bridge restricts reads to returned top-k product/image pairs, resolves canonical UUIDs through
the existing helper and fails on malformed/unknown/ambiguous/cross-product lineage. It neither
reranks nor silently filters a partially resolved response.

No vendor private data, IAM, audit, inventory, Listing state, Price, Currency, Brand, Category,
Size, Stock, image paths, storage keys, credentials or operational timestamps are exposed.
There are 2,093 current fixture rows in the view. Internal resolution of draft fixture Products
does not publish their draft Listings or authorize customer access.

## Runtime role and privilege matrix

`sahulat_visual_reader` is LOGIN-capable because the existing bridge opens a direct `psql`
connection. It is `NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT`,
has no memberships or owned relations, and has a connection limit of four. Its operational
defaults are read-only transactions and `search_path=pg_catalog`; privileges, not these mutable
defaults, enforce write denial.

| Surface / capability | Effective access in `sahulat_ai_dev` |
| --- | --- |
| Database connection | CONNECT |
| `catalog` namespace | USAGE, no CREATE |
| `catalog.visual_product_resolution_v1` | SELECT, without grant option |
| Catalog base tables / other views | No SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES or TRIGGER |
| IAM / Audit / Inventory / Integration schemas | No USAGE or data access |
| Database/schema DDL, ALTER/DROP of existing objects | Denied; no creation privilege, ownership or elevated membership |
| Temporary table creation | Denied |
| Elevated/broad reader role assumption | Denied |

No `GRANT ALL`, `SELECT ON ALL TABLES`, broad default privileges or role memberships are used.
The versioned artifact revokes inherited PUBLIC CREATE/TEMPORARY on **this target database**.
A role-specific REVOKE cannot negate PUBLIC grants; without this targeted change, temporary-table
DDL would remain possible. Existing direct privileges are preserved; `postgres` as owner is
unaffected. Future accounts needing TEMP must receive an explicit schema-owner-approved grant.
See [PostgreSQL REVOKE](https://www.postgresql.org/docs/18/sql-revoke.html).

The admission guard remains stricter than connection success: it rejects `postgres` before
launching psql, rejects all elevated role attributes/memberships, CREATE/TEMP, application writes
including column-level/inherited grants, unrelated application SELECT and view grant option.
Missing view or unsafe privilege drift fails closed; no guard is weakened to make import pass.

## Provisioning and schema ownership

Source: `database/provisioning/20260912_001_catalog_reader_access_v1.sql`.
This isolated forward provisioning artifact avoids editing the frozen Migration 001 or a shared
backend migration. It uses the existing `integration.schema_migrations` checksum history and
schema advisory lock. New view, role/grants and history record are committed transactionally.
Reapplication checks the normalized SQL SHA-256; drift fails instead of replacing the view.

The initial role is created only when absent. An existing managed role must be non-elevated,
unowned, membership-free and without extra application privileges. Existing credentials must
authenticate; the tool never silently rotates a password or strips an unsafe role's grants.
Reapplication does not duplicate views/roles/history or alter canonical business records.
The future designated schema/EF owner must retain this access artifact when establishing the
backend baseline; this is not a separate evolving backend migration chain.

## Credential mechanism

Use existing DATABASE_HOST/PORT/NAME/USER/PASSWORD/URL conventions through an explicit
`--database-env .env.visual-reader` argument. The administrative `.env` is neither changed nor
used by the runtime. Existing environment overrides must not substitute administrative values.

The provisioning tool generates a 256-bit URL-safe local password and a salted SCRAM-SHA-256
stored verifier using standard-library PBKDF2/HMAC primitives and the server's iteration policy.
Its encoding follows [PostgreSQL's SCRAM implementation](https://raw.githubusercontent.com/postgres/postgres/REL_18_STABLE/src/common/scram-common.c)
and is verified by successful actual PostgreSQL authentication. No plaintext password or verifier
is passed on command arguments or printed. The verifier is passed only through private stdin;
provisioning-session statement/duration/error-statement logging is disabled before setting it.
No `pg_hba.conf`, password-authentication policy or server-wide logging settings are changed.

Only a new root-local `.env.visual-reader` is generated; existing files are never overwritten.
It is excluded by the existing `.env.*` Git rule. Windows inheritance is removed before writing
the secret: the provisioning identity, SYSTEM and Administrators have full access, and the actual
workspace owner has read access when different. Unknown explicit ACL principals fail closed.
POSIX generation uses mode 0600. No secret value belongs in source, docs, tests or reports.
The tracked `integration/visual_bridge_v1/catalog-reader.env.example` has placeholders only.

Run from the checkout root with existing dependencies and administrative provisioning access:

```powershell
python -m integration.visual_bridge_v1.reader_access provision `
  --admin-env .env --reader-env .env.visual-reader
python -m integration.visual_bridge_v1.reader_access verify `
  --reader-env .env.visual-reader
```

If a role already exists but its protected credential reference is unavailable, provisioning
refuses with `existing_reader_credential_reference_required`; an operator must supply it.
For explicit manual password maintenance only, use the interactive local psql `\password`
command and securely update the protected configuration out of band. Never put a real password
in a command line or committed SQL template. Rotation/recovery is not implemented by this gate.

## Verification and live bridge

Tests use generated temporary databases and unique test roles. Prohibited operations are
attempted in transactions explicitly switched to READ WRITE, followed by unconditional rollback
or connection rollback on error. Thus denial proves permissions rather than read-only defaults.
They cover INSERT/UPDATE/DELETE/TRUNCATE, Catalog/public/TEMP CREATE, ALTER, DROP, base-table and
unrelated/schema credential reads, and SET ROLE escalation. They also cover superuser/CREATEDB/
CREATEROLE/replication/RLS bypass/membership/column-grant/grant-option drift, checksum idempotency,
password non-rotation, protected-file integrity and real test-DB canonical resolution.

```powershell
$env:RUN_DATABASE_TESTS='1'
python -m pytest tests/visual_bridge_v1 tests/api -q
python -m pytest tests/database -q
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m mypy integration
python -m pip check

$env:HF_HUB_OFFLINE='1'
$env:VISUAL_DEVICE='cpu'
python -m integration.visual_bridge_v1.smoke `
  --index artifacts/catalogue-openclip.npz `
  --index-sha256 cd6c6d6e53f7f7ad94de3f555cca71685e5905d50eb36f54d7c87308e0a1084b `
  --source-system khaadi-v1 --database-env .env.visual-reader
```

The measured cached OpenCLIP -> unchanged loopback API -> bridge -> scoped reader smoke resolved
five canonical Products, preserving raw ranking positions/identities/scores. No catalogue
embeddings or model artifact were rebuilt. Operational full-business-table fingerprints match
before/after provisioning and smoke; the one technical access-history row is intentionally
excluded from business-row parity.

## Limitations and stop

This is internal development access, not tenant authorization, production publication or a
security/SLO certification. Owner-rights view behavior must be reviewed if future RLS/visibility
policies are introduced; none are enabled or changed here. PostgreSQL catalog metadata and
standard PUBLIC defaults outside the target database are not redesigned. No other database ACL
or HBA rule is altered; claims/tests cover `sahulat_ai_dev`, not global database isolation.

No text queries/labels, FTS, BM25, dense retrieval, RRF, frontend, authentication flows, Commerce,
voice or vendor RAG modules were edited. Stop after reader access and bridge verification.
