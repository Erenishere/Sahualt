# ADR-PLATFORM-001: database migration ownership

Status: accepted; explicit SQL baseline and first backend business migration implemented, environment verification pending.

## Context

The canonical catalog migration `20260910_001_catalog_core_v1.sql` creates the shared `iam`, `catalog`, `inventory`, `integration`, and `audit` schemas. It records a checksum in `integration.schema_migrations`. The existing `20260926_002_search_lexical_v1.sql` and `20260926_003_text_dense_prototype_v1.sql` add ML-owned `search` objects through the same checksum-verified runner. These migration files may already be present in development databases. The catalog migration uses `uuidv7()`, so all environments applying it must use PostgreSQL 18.

## Decision

1. Migration 001 is immutable. Do not edit its SQL, change its checksum, or recreate its tables through EF Core.
2. Migrations 002 and 003 remain ML-owned research/search migrations. Preserve their files and checksums. They do not grant ML ownership of `iam`, `catalog`, `inventory`, `assistant`, or future `commerce` objects.
3. All new business DDL is backend-owned, additive, versioned, and reviewed against both a fresh PostgreSQL 18 database and an existing database with 001/002/003 already applied. Runtime API startup never applies migrations.
4. Do not introduce a second writer for any schema. Migration `20261011_004_backend_business_baseline_v1` is the no-op backend baseline and requires history for 001/002/003. Migration `20261011_005_commerce_foundation_v1` is the first additive backend-owned business migration. EF Core is not part of this migration chain.
5. The deployment migration role is separate from all runtime roles. Backend and ML runtime logins receive only the privileges their operations require. The PostgreSQL admin login is not an application connection string.
6. Every migration release needs a backup/restore plan, checksum check, and explicit verification of preserved pre-upgrade rows. Destructive DDL requires a separate reviewed migration plan.

## Required verification before the first new business migration

- Fresh install: empty PostgreSQL 18 plus pgvector, apply 001/002/003 and the no-op backend baseline, then the new migration.
- Upgrade: snapshot an existing 001/002/003 database, apply the baseline and new migration, then compare row counts and representative records before and after.
- Confirm that `integration.schema_migrations` still contains the original IDs and matching checksums.
- Confirm that only the migration role can perform DDL; backend and ML runtime roles cannot.
- Confirm that API startup with insufficient DDL privileges succeeds without attempting schema changes.

## Consequences

The explicit runner now plans and applies migrations 001-005 with checksum guards. Runtime API identities cannot perform DDL. Fresh-install and upgrade preservation gates still require PostgreSQL 18 with pgvector; until those pass, migrations 004/005 and their grants are implemented but not deployment-verified.
