# Catalog Reader Access V1 validation

Date: 2026-09-12. Owner: Adeel's isolated ML/integration workstream.

**CATALOG-READER-ACCESS-V1: GREEN. VISUAL-INTEGRATION-BRIDGE-V1: GREEN.**
Live application-role canonical resolution is now VERIFIED, not merely synthetic or HTTP-only.

## Audit and implementation

The pre-change read-only audit measured PostgreSQL 18.6 / `sahulat_ai_dev`, only the `postgres`
superuser, no existing Catalog views, no reader/grant definitions and null application-schema
ACLs. Migration 001 grants no PUBLIC table access. No existing suitable role/projection could be
reused. Its default database ACL did inherit PUBLIC TEMP, which had to be removed in the target
database to deny temporary-table DDL independently of read-only transaction defaults.

Created:

- Direct-login runtime role `sahulat_visual_reader`.
- Minimal owner-rights, security-barrier join view `catalog.visual_product_resolution_v1`.
- Isolated checksum-verified forward provisioning artifact, not an edit to frozen Migration 001.
- Safe provisioning/verification entry point, protected local credential and placeholder example.
- Focused access/security tests in Adeel's existing isolated bridge test directory.

The bridge's private reader SQL is narrowed to the view. Its types, existing canonical helper,
Visual API contract, encoder, exact cosine/MAX aggregation and ranking semantics are unchanged.
The guard is strengthened to deny TEMP, any role membership and view grant option; the early
`postgres` rejection remains unchanged. The existing join-integrity test now checks the view's
versioned definition while preserving both image/product and source-namespace assertions.

No application authentication, backend/.NET project, IAM flow or unrelated teammate module is
introduced. Details/commands: [CATALOG-READER-ACCESS-V1](../docs/CATALOG-READER-ACCESS-V1.md).

## Exact accessible surface and actual role profile

Effective target-database privileges: CONNECT, USAGE on catalog, SELECT without grant option on
**one view only**. No base-table SELECT is required or granted.

View columns, in order:

```text
source_system
external_product_id
external_image_id
product_id
image_id
name
description
blocked
```

Actual runtime queries measured 2,093 view rows and 400 unique canonical Products. Its underlying
joins prove the Product/Image association and matching source namespace; archive timestamps are
reduced to one Boolean rather than exposed. No Listing, inventory, IAM, Audit, vendor private
data, price, currency, stock, Size, Brand, Category, storage/image paths or credentials are exposed.

| Actual runtime characteristic | Verified result |
| --- | --- |
| LOGIN | YES, authenticated using generated SCRAM credential |
| Superuser / CREATEDB / CREATEROLE / replication / BYPASSRLS | NO / NO / NO / NO / NO |
| Role inheritance / memberships | NO / 0 |
| Owned relations | 0 |
| Database CREATE / TEMP | NO / NO |
| Private schema USAGE: IAM, Audit, Inventory, Integration | NO for each |
| Application-schema SELECT surface | Exactly `catalog.visual_product_resolution_v1` |
| Catalog writes / DDL / elevation / unrelated data reads | Denied |

PostgreSQL system catalog metadata used by the guard remains ordinarily visible. Claims are
scoped to `sahulat_ai_dev`; inherited PUBLIC defaults in other databases are not changed and
global database isolation is not claimed. No other database ACL/HBA/auth policy is modified.

## Security verification

Dedicated tests create only generated temporary databases and unique temporary roles, provision
the exact versioned access artifact and authenticate directly as the resulting reader. Forbidden
operations run in rollback contexts after **SET TRANSACTION READ WRITE**, proving real privilege
denial rather than relying on mutable read-only defaults. SQLSTATE `42501` is required.

Verified denial of:

- INSERT, UPDATE, DELETE and TRUNCATE on Catalog.
- CREATE in Catalog/public, CREATE TEMP, ALTER Catalog and DROP the projection.
- Base Catalog table reads, IAM, Audit, Inventory, Outbox and `pg_authid` credential reads.
- SET ROLE postgres and SET ROLE pg_read_all_data.

Privilege-drift tests independently introduce superuser, CREATEDB, CREATEROLE, replication,
BYPASSRLS, role membership, column SELECT, column UPDATE and view grant option into a temporary
test reader, prove guard rejection, then restore the original profile. Checksum drift is rejected;
unchanged reapplication is idempotent and never rotates an existing password. File tests prove
exclusive creation, consistent DATABASE_PASSWORD/URL, admin rejection before connection, private
stdin verifier delivery and fail-closed behavior for an unexpected explicit Windows ACL principal.

The actual live role was independently checked with safe zero-row INSERT/UPDATE/DELETE attempts,
base-table and IAM/Audit/Inventory/Outbox reads restricted to WHERE false, and both SET ROLE
attempts. **All ten attempts failed with permission denial**. No live TRUNCATE, ALTER or DROP was
attempted; those operations are proven by the same provisioned profile in isolated rollback-safe
tests, with live effective privileges and ownership independently confirming their absence.
No credentials/error text or privileged rows are printed by these checks.

## Live OpenCLIP -> API -> bridge -> reader -> canonical DB

Executed the existing cached-model smoke with `HF_HUB_OFFLINE=1`, CPU and `.env.visual-reader`.
It started the unchanged existing FastAPI app on an ephemeral loopback-only port, one worker,
access logs off, proxy headers untrusted. One synthetic 32x32 PNG was sent unchanged through the
typed client. This is integration test input, not a human query or benchmark label.

Measured result:

```json
{
  "api_ranked_products": 5,
  "api_smoke": "PASSED",
  "bridge_version": "visual-integration-bridge-v1",
  "catalog_writes": 0,
  "gate": "GREEN",
  "live_canonical_resolution": "VERIFIED",
  "ranking_preserved": true,
  "resolved_products": 5,
  "source_system": "khaadi-v1"
}
```

Both the bridge invariant and the smoke compare ranks, external product/image identities and
original scores without sorting/reranking. Each returned canonical Product/Image UUID resolves
through the live view and original canonical helper. No partial response or guessed ID is allowed.
Cached OpenCLIP selection, preprocessing, embeddings/index, MAX aggregation, tie rules and
EVAL-VISUAL-V1 remain unchanged. No new model download, stored embedding, retriever or evaluation
result is produced; the existing model's normal query-image encoding is exercised only.

## Zero-write/state and checksum evidence

Before/after provisioning, idempotent reapplication, live smoke and live negative security probes,
the complete operational business-state fingerprint remains:

`1cd44b034805a2aff72a67735589220b94e345cd37eb296cbb80197c3d028c59`.

This is SHA-256 over sorted JSON of per-business-table row counts/ordered-row MD5 fingerprints,
not the fixture semantic checksum or PRODUCT-TEXT-V1 artifact identity. It excludes only technical
migration history. No business INSERT/UPDATE/DELETE, trigger/outbox event or schema mutation of
business tables was issued by the provisioning/reader.

| Preserved state | Count |
| --- | --- |
| Products / Variants / Draft Listings | 400 / 400 / 400 |
| Product Images / Image External Refs | 2,093 / 2,093 |
| Product External Refs | 400 |
| Vendors (existing fixture tenant) | 1 |
| Categories / IAM Users / Memberships | 0 / 0 / 0 |
| Inventory / Outbox / Audit rows | 0 / 0 / 0 |

Migration 001 SQL checksum remains:
`956ac05cbf94f1feae03b14feb7d69210d39b3e9e133e2f897a0928017a1934d`.

New provisioning source/history checksum:
`047dce6ed3dfd8cab91f40436c6109c2a0a8d643a8b6c584a3b17c4af0b689ab`.
Technical history contains each version once. Reapplication reports role reused, same data/hash
and 2,093 view rows; no new role/view/history duplication or password rotation.

Unchanged Visual HTTP OpenAPI SHA-256:
`9c6fe17c1fd69190734b47351fe148cf85ac8ae1999df59e4a2b8493718e00a9`.
Existing cached index SHA-256:
`cd6c6d6e53f7f7ad94de3f555cca71685e5905d50eb36f54d7c87308e0a1084b`.
No Search/Commerce/Analytics schema, FTS/tsvector/tsquery column or vector extension is created.

## Tests and static analysis

Python 3.12.10; database tests explicitly enabled with RUN_DATABASE_TESTS=1.

| Verification | Executed result |
| --- | --- |
| New reader-access suite | 43 passed in final full run: 11 unit/ACL, 32 database/security |
| New unit/ACL dedicated run | 11 passed, 32 deselected |
| Initial access + guard + reader targeted run | 67 passed before the final extra ACL regression |
| Bridge + API dedicated run | 216 passed before the final extra ACL regression; all 217 current cases passed in the final full run |
| Current bridge directory | 141 passed in final full run |
| Existing API directory | 76 passed |
| Existing database directory dedicated run | 59 passed |
| Database-marked cases | 91 passed in final full run |
| Full repository | **546 passed, 2 opt-in model tests skipped**, 0 failures, 85.53 seconds |
| Ruff lint / formatting | PASS / PASS, 130 Python files formatted |
| mypy source / integration | PASS, 72 / 11 source files |
| Dependency validation | PASS: pip check reports no broken requirements |
| .NET analysis | Not applicable: no .NET introduced |

The two existing Starlette/AnyIO deprecation warnings remain visible; no pins, guards or tests
were weakened to suppress them. Visual/Fixture Ingestion/Database regressions remain green.
The separate real cached OpenCLIP smoke passed; skipped opt-in models are not reported as run.

## Complete file inventory and secrets

Added source/documentation files:

- `database/provisioning/20260912_001_catalog_reader_access_v1.sql`
- `integration/visual_bridge_v1/reader_access.py`
- `integration/visual_bridge_v1/catalog-reader.env.example`
- `tests/visual_bridge_v1/test_reader_access.py`
- `docs/CATALOG-READER-ACCESS-V1.md`
- `reports/catalog_reader_access_v1_validation.md`

Modified Adeel-owned bridge files:

- `integration/visual_bridge_v1/catalogue.py`: view-only read and stronger privilege guard.
- `integration/visual_bridge_v1/smoke.py`: raw API versus canonical result ranking comparison.
- `tests/visual_bridge_v1/test_catalogue.py`: view/source-join integrity assertions preserved.
- `docs/VISUAL-INTEGRATION-BRIDGE-V1.md`: current GREEN status/read surface.
- `reports/visual_integration_bridge_v1_validation.md`: follow-up link; original RED evidence retained.

Generated **local-only, ignored secret configuration**: `.env.visual-reader`.
Its password/URL/verifier are not present in any committed/source file or report. Windows ACL
verification showed only the provisioning identity, workspace owner (read), SYSTEM and
Administrators. The tracked example contains placeholders only; the administrative `.env` and
`.env.example` are unchanged. The existing `.env.*` Git exclusion already protects the local file.
No Git repository metadata/commit exists here; no init, commit, branch, push or secret staging
was performed. Review used this explicit inventory, source checks and frozen contract hashes.

## Limitations and stopping point

No operational blocker remains in this local gate. This is internal read-only integration, not
public deployment, tenant authorization, product publication or production SLO certification.
Role provisioning is schema-owner-operated; future EF/RLS/visibility baseline decisions must
retain/review this purpose-specific view rather than silently broadening its grants. Cross-database
PUBLIC defaults are outside this gate; no global database isolation claim is made.

No teammate-owned text-query, labeling, adjudication, EVAL-TEXT-V1, FTS/backend-readiness or shared
application module was modified. No text retrieval, FTS, BM25, dense retrieval, RRF, frontend,
authentication flows, Commerce/offers, vendor RAG or voice work was implemented. No query/relevance
labels or missing catalog attributes were fabricated. Stop after scoped reader and bridge verification.
