# PostgreSQL baseline

Sahulat AI local development uses PostgreSQL 18 with pgvector 0.8.6, pinned in the root `docker-compose.yml`. The canonical catalog migration uses PostgreSQL 18's `uuidv7()` function. The PostgreSQL 18 image stores its data under `/var/lib/postgresql/18/docker`, so the Compose named volume is mounted at `/var/lib/postgresql`.

Copy the root `.env.example` to `.env` and set a local `POSTGRES_ADMIN_PASSWORD` before starting Compose. This admin login is for database initialization and explicit migration/provisioning operations only. The backend and ML services must receive separate, least-privilege credentials; neither should use `postgres`. Compose does not apply migrations or create runtime roles automatically.

Do not point this PG18 container at an existing PG16 data directory or delete an old volume to make it start. A PostgreSQL major-version upgrade requires a tested `pg_upgrade` or dump/restore procedure, including a backup and post-upgrade verification. The new named volume is for fresh PG18 environments; existing PG16 data remains separate until an explicit migration plan is approved.

For a fresh local database, start the `postgres` service, then run `scripts/apply-platform-migrations.ps1` from the repository root. With no arguments it prints the three immutable migration IDs and normalized SHA-256 checksums without connecting to Docker. Use `-Apply` to run those exact files through PostgreSQL 18's `psql` inside the container. The script checks `uuidv7()` and pgvector availability before writing, and the SQL files themselves enforce idempotency and checksum matching in `integration.schema_migrations`. The migrations directory is mounted read-only in the container. This runner is for local Compose; staging/production need a deployment-controlled migrator and backup procedure.

For an already-running local PostgreSQL 18 Windows service, the same runner
supports `-Local -DatabaseName sahulat_ai_dev` (the local default). It remains plan-only until `-Apply`
is also given, accepts loopback hosts only, and uses `psql -w` with a private
PostgreSQL credential configured outside the repository. It never prompts for,
prints, or stores a password. Confirm the intended database name and backup
state before applying migrations. The three backend capability-role scripts
under `backend/database/provisioning/` are separate from schema migrations.
After catalog migration 001, `scripts/verify-local-catalog-db.ps1 -Apply`
applies those three NOLOGIN capability-role grants and runs a draft insert,
viewer/cross-vendor denial, and reader check in a rolled-back transaction. It
does not create login passwords or leave fixture rows behind. Its default mode
is plan-only. A database administrator must separately create dedicated LOGIN
roles and grant these capabilities before starting the API with runtime URLs.

```powershell
docker compose up -d postgres
./scripts/apply-platform-migrations.ps1
./scripts/apply-platform-migrations.ps1 -Apply
```
